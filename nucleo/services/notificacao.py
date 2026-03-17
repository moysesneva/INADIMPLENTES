import logging
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from ..models import Acordo, RegraNotificacao, HistoricoNotificacao, RegistroAuditoria, AlertaFinanceiro

logger = logging.getLogger(__name__)

def preencher_template(template_text, acordo):
    """
    Substitui os placeholders {nome}, {acordo_id}, {valor}, {escola}, {link_portal}
    """
    valor_formatado = f"R$ {acordo.valor_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    base_url = getattr(settings, 'PORTAL_BASE_URL', 'http://localhost:8000')
    link_portal = f"{base_url}/p/{acordo.devedor.uuid_acesso}/"
    
    placeholders = {
        '{nome}': acordo.devedor.nome,
        '{acordo_id}': str(acordo.numero_acordo),
        '{valor}': valor_formatado,
        '{escola}': getattr(acordo.devedor.dividas.first(), 'escola', 'CNA'),
        '{link_portal}': link_portal,
    }
    
    content = template_text
    for key, val in placeholders.items():
        content = content.replace(key, val)
    return content

def avaliar_elegibilidade(acordo, regra):
    """
    Verifica se um acordo é elegível para uma regra específica (Baseado em Status).
    """
    if acordo.status != regra.status_alvo:
        return False
        
    limite = acordo.data_acordo + timedelta(days=regra.dias_gatilho)
    if timezone.now() < limite:
        return False
        
    ja_enviada = HistoricoNotificacao.objects.filter(
        acordo=acordo, 
        regra=regra, 
        status__in=['SUCESSO', 'SIMULADO']
    ).exists()
    
    return not ja_enviada

def enviar_notificacao_email(acordo, regra, usuario_executor=None, alerta=None):
    """
    Envio de E-mail vinculado a um acordo (e opcionalmente a um alerta).
    """
    destinatario = acordo.devedor.email
    if not destinatario:
        return False, "E-mail não cadastrado no devedor."

    assunto = preencher_template(regra.assunto_email or f"CNA: Comunicado #{acordo.numero_acordo}", acordo)
    corpo = preencher_template(regra.corpo_template, acordo)
    
    historico = HistoricoNotificacao.objects.create(
        acordo=acordo, regra=regra, alerta=alerta, canal='EMAIL',
        destinatario=destinatario, conteudo_enviado=corpo, status='PENDENTE'
    )

    try:
        send_mail(
            assunto, corpo,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'cobranca@cna.com.br'),
            [destinatario], fail_silently=False,
        )
        historico.status = 'ENVIADO'
        historico.mensagem_id_externo = f"MAIL_{historico.id}_{timezone.now().timestamp()}"
        historico.save()
        
        RegistroAuditoria.objects.create(
            usuario=usuario_executor, acao='NOTIFICACAO_ENVIADA',
            detalhes=f"E-mail [{regra.nome}] enviado p/ {destinatario} (Alerta: {alerta.id if alerta else 'N/A'})",
            registro_id=f"Acordo_{acordo.numero_acordo}"
        )
        return True, None
    except Exception as e:
        historico.status = 'FALHA'
        historico.erro_log = str(e)
        historico.save()
        
        RegistroAuditoria.objects.create(
            usuario=usuario_executor, acao='NOTIFICACAO_FALHA',
            detalhes=f"Falha ao enviar e-mail [{regra.nome}]: {str(e)}",
            registro_id=f"Acordo_{acordo.numero_acordo}"
        )
        return False, str(e)

def enviar_notificacao_whatsapp_mock(acordo, regra, usuario_executor=None, alerta=None):
    """
    Simulação de envio via WhatsApp vinculado a um acordo (e opcionalmente a um alerta).
    """
    destinatario = acordo.devedor.celular or acordo.devedor.telefone
    if not destinatario:
        return False, "Nenhum telefone de contato ou celular cadastrado."

    corpo = preencher_template(regra.corpo_template, acordo)
    conteudo_simulado = f"[MOCK WHATSAPP SEND TO {destinatario}]\n{corpo}"
    
    historico = HistoricoNotificacao.objects.create(
        acordo=acordo, regra=regra, alerta=alerta, canal='WHATSAPP',
        destinatario=destinatario, conteudo_enviado=conteudo_simulado, 
        status='SIMULADO'
    )
    # Atribui ID externo mockado após criação para ter o ID real
    historico.mensagem_id_externo = f"WPP_MOCK_{historico.id}_{timezone.now().timestamp()}"
    historico.save()

    RegistroAuditoria.objects.create(
        usuario=usuario_executor, acao='NOTIFICACAO_ENVIADA',
        detalhes=f"WhatsApp MOCK [{regra.nome}] simulado p/ {destinatario} (Alerta: {alerta.id if alerta else 'N/A'})",
        registro_id=f"Acordo_{acordo.numero_acordo}"
    )
    
    return True, None

def atualizar_status_notificacao(historico_id, novo_status, timestamp=None, erro=None):
    """
    Atualiza o status de uma notificação e reflete no ciclo de vida do alerta se necessário.
    """
    try:
        historico = HistoricoNotificacao.objects.get(pk=historico_id)
    except HistoricoNotificacao.DoesNotExist:
        return False, "Notificação não encontrada."

    timestamp = timestamp or timezone.now()
    historico.status = novo_status
    
    if novo_status == 'ENTREGUE':
        historico.data_entrega = timestamp
    elif novo_status == 'LIDO':
        historico.data_leitura = timestamp
        # Se for LIDO, marcamos o alerta como EM_TRATAMENTO (reconhecido pelo devedor)
        if historico.alerta and historico.alerta.status == 'ABERTO':
            historico.alerta.status = 'EM_TRATAMENTO'
            historico.alerta.save()
            
            RegistroAuditoria.objects.create(
                acao='ALERTA_ATUALIZADO',
                detalhes=f"Alerta #{historico.alerta.id} movido para EM_TRATAMENTO (Notificação Lida)",
                registro_id=str(historico.alerta.acordo.id)
            )
            
    elif novo_status == 'FALHA' and erro:
        historico.erro_log = erro

    historico.save()
    return True, None

def processar_motor_regras(usuario_executor=None):
    """
    Varre regras ativas e acordos elegíveis (Fluxo Clássico por Status).
    """
    regras_ativas = RegraNotificacao.objects.filter(ativo=True).exclude(
        slug__startswith='alerta-' # Ignora regras vinculadas a alertas no fluxo clássico
    )
    contador_sucesso = 0
    erros = []
    
    for regra in regras_ativas:
        acordos_candidatos = Acordo.objects.filter(status=regra.status_alvo)
        for acordo in acordos_candidatos:
            if avaliar_elegibilidade(acordo, regra):
                if regra.canal == 'EMAIL':
                    sucesso, msg = enviar_notificacao_email(acordo, regra, usuario_executor)
                elif regra.canal == 'WHATSAPP':
                    sucesso, msg = enviar_notificacao_whatsapp_mock(acordo, regra, usuario_executor)
                else:
                    sucesso = False
                    msg = f"Canal {regra.canal} não suportado."

                if sucesso:
                    contador_sucesso += 1
                else:
                    erros.append(f"Regra {regra.nome} - Acordo #{acordo.numero_acordo}: {msg}")
                    
    return contador_sucesso, erros

def processar_alertas_comunicacao(usuario_executor=None):
    """
    Converte alertas financeiros elegíveis em tentativas de notificação (Fluxo Fase G2).
    """
    eligible_types = ['PARCELA_ATRASADA', 'RISCO_PROXIMO', 'ACORDO_RISCO']
    alertas_abertos = AlertaFinanceiro.objects.filter(
        status='ABERTO', 
        tipo_alerta__in=eligible_types
    )
    
    # Mapeamento Tipo -> Slug da Regra
    tipo_to_slug = {
        'PARCELA_ATRASADA': 'alerta-parcela-atrasada',
        'RISCO_PROXIMO': 'alerta-risco-proximo',
        'ACORDO_RISCO': 'alerta-acordo-risco',
    }
    
    count = 0
    erros = []
    
    for alerta in alertas_abertos:
        slug = tipo_to_slug.get(alerta.tipo_alerta)
        if not slug:
            continue
            
        try:
            regra = RegraNotificacao.objects.get(slug=slug, ativo=True)
        except RegraNotificacao.DoesNotExist:
            continue
            
        # Idempotência: Checa se já existe notificação vinculada a este ALERTA específico (não falha)
        ja_notificado = HistoricoNotificacao.objects.filter(
            alerta=alerta,
            status__in=['ENVIADO', 'ENTREGUE', 'LIDO', 'SIMULADO', 'PENDENTE']
        ).exists()
        
        if ja_notificado:
            continue
            
        # Envio centralizado
        if regra.canal == 'EMAIL':
            sucesso, msg = enviar_notificacao_email(alerta.acordo, regra, usuario_executor, alerta=alerta)
        elif regra.canal == 'WHATSAPP':
            sucesso, msg = enviar_notificacao_whatsapp_mock(alerta.acordo, regra, usuario_executor, alerta=alerta)
        else:
            sucesso = False
            msg = f"Canal {regra.canal} não suportado."
            
        if sucesso:
            count += 1
        else:
            erros.append(f"Alerta #{alerta.id} ({alerta.tipo_alerta}): {msg}")
            
    return count, erros
