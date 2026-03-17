from django.utils import timezone
from ..models import Acordo, Parcela, AlertaFinanceiro, RegistroAuditoria
import datetime

class AlertasService:
    @staticmethod
    def gerar_alerta(acordo, parcela, tipo, severidade, descricao):
        """
        Cria um alerta de forma idempotente.
        Se já existir um alerta ABERTO do mesmo tipo para o mesmo objeto, ignore.
        """
        # Idempotência: Verifica se já existe alerta ABERTO para este contexto
        if parcela:
            existe = AlertaFinanceiro.objects.filter(
                acordo=acordo,
                parcela=parcela,
                tipo_alerta=tipo,
                status='ABERTO'
            ).exists()
        else:
            existe = AlertaFinanceiro.objects.filter(
                acordo=acordo,
                parcela__isnull=True,
                tipo_alerta=tipo,
                status='ABERTO'
            ).exists()

        if not existe:
            alerta = AlertaFinanceiro.objects.create(
                acordo=acordo,
                parcela=parcela,
                tipo_alerta=tipo,
                severidade=severidade,
                descricao=descricao
            )
            
            # Registrar auditoria
            RegistroAuditoria.objects.create(
                acao='ALERTA_GERADO',
                detalhes=f"Alerta {tipo} ({severidade}): {descricao}",
                registro_id=str(acordo.id)
            )
            return alerta
        return None

    @classmethod
    def verificar_parcelas_atrasadas(cls):
        """Detecta parcelas com vencimento no passado e não pagas."""
        hoje = timezone.now().date()
        parcelas_atrasadas = Parcela.objects.filter(
            vencimento__lt=hoje,
            status__in=['PENDENTE', 'ATRASADO']
        ).exclude(status='PAGO')

        count = 0
        for p in parcelas_atrasadas:
            cls.gerar_alerta(
                acordo=p.acordo,
                parcela=p,
                tipo='PARCELA_ATRASADA',
                severidade='MEDIA',
                descricao=f"Parcela {p.numero} vencida em {p.vencimento.strftime('%d/%m/%Y')}."
            )
            count += 1
        return count

    @classmethod
    def verificar_acordos_em_risco(cls):
        """Detecta acordos com alto risco (ex: 2 ou mais parcelas atrasadas)."""
        hoje = timezone.now().date()
        acordos_ativos = Acordo.objects.exclude(status__in=['CANCELADO', 'PAGO'])
        
        count = 0
        for acordo in acordos_ativos:
            atrasadas = acordo.detalhe_parcelas.filter(
                vencimento__lt=hoje,
                status__in=['PENDENTE', 'ATRASADO']
            ).exclude(status='PAGO').count()

            if atrasadas >= 2:
                cls.gerar_alerta(
                    acordo=acordo,
                    parcela=None,
                    tipo='ACORDO_RISCO',
                    severidade='ALTA',
                    descricao=f"Risco Crítico: Acordo com {atrasadas} parcelas em atraso."
                )
                count += 1
        return count

    @classmethod
    def verificar_risco_proximo_vencimento(cls):
        """Detecta parcelas que vencem em 1 ou 2 dias (Alerta Proativo)."""
        hoje = timezone.now().date()
        amanha = hoje + datetime.timedelta(days=1)
        depois_amanha = hoje + datetime.timedelta(days=2)
        
        parcelas_proximas = Parcela.objects.filter(
            vencimento__in=[amanha, depois_amanha],
            status='PENDENTE'
        )

        count = 0
        for p in parcelas_proximas:
            cls.gerar_alerta(
                acordo=p.acordo,
                parcela=p,
                tipo='RISCO_PROXIMO',
                severidade='BAIXA',
                descricao=f"Lembrete: Parcela {p.numero} vence em {p.vencimento.strftime('%d/%m/%Y')}."
            )
            count += 1
        return count

    @classmethod
    def verificar_quebra_acordo(cls):
        """Detecta acordos que o sistema já marcou como QUEBRADO."""
        acordos_quebrados = Acordo.objects.filter(status='QUEBRADO')
        
        count = 0
        for acordo in acordos_quebrados:
            cls.gerar_alerta(
                acordo=acordo,
                parcela=None,
                tipo='QUEBRA_ACORDO',
                severidade='ALTA',
                descricao="Quebra Detectada: Acordo não honrado conforme cronograma."
            )
            count += 1
        return count

    @classmethod
    def atualizar_alerta_para_resolvido(cls, alerta, motivo):
        """Move alerta para RESOLVIDO centralizadamente."""
        if alerta.status != 'RESOLVIDO':
            alerta.status = 'RESOLVIDO'
            alerta.save()
            
            RegistroAuditoria.objects.create(
                acao='ALERTA_RESOLVIDO',
                detalhes=f"Alerta #{alerta.id} RESOLVIDO: {motivo}",
                registro_id=str(alerta.acordo.id)
            )

    @classmethod
    def auto_resolver_alertas(cls):
        """
        Varre alertas ABERTOS/TRATAMENTO e verifica se a condição financeira sumiu.
        Ex: Parcela paga -> Alerta de Parcela Atrasada resolvido.
        """
        alertas_pendentes = AlertaFinanceiro.objects.filter(status__in=['ABERTO', 'EM_TRATAMENTO'])
        count = 0
        
        for alerta in alertas_pendentes:
            if alerta.tipo_alerta == 'PARCELA_ATRASADA' and alerta.parcela:
                if alerta.parcela.status == 'PAGO':
                    cls.atualizar_alerta_para_resolvido(alerta, "Parcela identificada como PAGA.")
                    count += 1
            
            elif alerta.tipo_alerta == 'QUEBRA_ACORDO':
                if alerta.acordo.status != 'QUEBRADO':
                    cls.atualizar_alerta_para_resolvido(alerta, f"Acordo mudou de status para {alerta.acordo.status}.")
                    count += 1
                    
            elif alerta.tipo_alerta == 'ACORDO_RISCO':
                # Re-calcula atrasadas
                hoje = timezone.now().date()
                atrasadas = alerta.acordo.detalhe_parcelas.filter(
                    vencimento__lt=hoje,
                    status__in=['PENDENTE', 'ATRASADO']
                ).exclude(status='PAGO').count()
                
                if atrasadas < 2:
                    cls.atualizar_alerta_para_resolvido(alerta, f"Risco reduzido: apenas {atrasadas} parcelas em atraso.")
                    count += 1

            elif alerta.tipo_alerta == 'RISCO_PROXIMO' and alerta.parcela:
                if alerta.parcela.status == 'PAGO' or alerta.parcela.vencimento < timezone.now().date():
                    cls.atualizar_alerta_para_resolvido(alerta, "Vencimento passou ou parcela foi paga.")
                    count += 1
                    
        return count

    @classmethod
    def processar_tudo(cls):
        """Executa todos os motores de detecção e resolução."""
        # Primeiro, forçamos a atualização dos status dos acordos baseados nas parcelas
        for acordo in Acordo.objects.exclude(status__in=['CANCELADO', 'PAGO']):
            acordo.atualizar_status_por_parcelas()

        # Resolve o que não é mais risco
        resolvidos = cls.auto_resolver_alertas()

        return {
            'atrasadas': cls.verificar_parcelas_atrasadas(),
            'em_risco': cls.verificar_acordos_em_risco(),
            'proximos': cls.verificar_risco_proximo_vencimento(),
            'quebras': cls.verificar_quebra_acordo(),
            'resolvidos': resolvidos,
        }
