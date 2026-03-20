import datetime
from django.db.models import Sum, Min, Count, Q
from .estatisticas import EstatisticasService

class MensageriaService:
    """
    Serviço responsável por gerar e formatar mensagens de abordagem operacional.
    """
    
    TEMPLATES = {
        'alto_valor': (
            "Olá, {nome}! Tudo bem?\n\n"
            "Identifiquei aqui uma oportunidade especial para regularizarmos seu contrato de maior valor com condições diferenciadas de desconto.\n\n"
            "Podemos conversar para encontrar uma parcela que se ajuste melhor ao seu planejamento hoje?"
        ),
        'atraso_critico': (
            "Olá, {nome}! Gostaria de te ajudar a resolver uma pendência que consta aqui em nosso sistema.\n\n"
            "Notei que o atraso já está considerável e meu objetivo é evitar qualquer restrição adicional ao seu nome.\n\n"
            "Vamos fechar um acordo rápido e com condições facilitadas agora?"
        ),
        'recorrencia': (
            "Olá, {nome}! Como vai?\n\n"
            "Vi que acumulamos algumas pendências diferentes aqui. Que tal unificarmos tudo em um único plano de pagamento para facilitar sua organização?\n\n"
            "Dessa forma, você resolve tudo de uma vez com uma parcela que cabe no seu bolso. Vamos analisar?"
        ),
        'misto': (
            "Olá, {nome}! Estou entrando em contato para revisarmos sua situação atual e oferecer uma solução completa para todas as suas pendências.\n\n"
            "Como seu caso tem prioridade, consegui liberar uma margem maior de negociação para resolvermos isso hoje mesmo.\n\n"
            "Pode falar agora para vermos os detalhes?"
        ),
        'fallback': (
            "Olá, {nome}! Identificamos algumas pendências em aberto e gostaríamos de oferecer ajuda para regularizar sua situação com as melhores condições do dia.\n\n"
            "Qual seria o melhor horário para conversarmos sobre uma proposta de acordo?"
        )
    }

    @classmethod
    def gerar_mensagem_whatsapp(cls, devedor, segmento_fornecido=None):
        """
        Gera uma mensagem personalizada baseada no segmento de risco.
        """
        # 1. Resolver o primeiro nome para um tom mais humano
        nome_completo = devedor.nome or "Cliente"
        primeiro_nome = nome_completo.split()[0].title()

        # 2. Se o segmento não foi fornecido, resolvemos via EstatisticasService
        segmento = segmento_fornecido
        if not segmento:
            hoje = datetime.date.today()
            # Calculamos os indicadores necessários
            resumo = devedor.dividas.aggregate(
                total_aberto=Sum('valor_atual'),
                qtd_dividas=Count('id'),
                vencimento_mais_antigo=Min('vencimento', filter=Q(vencimento__lt=hoje))
            )
            
            total_float = float(resumo['total_aberto'] or 0)
            dias_overdue = 0
            if resumo['vencimento_mais_antigo']:
                dias_overdue = (hoje - resumo['vencimento_mais_antigo']).days
            
            ctx = EstatisticasService.calcular_score_e_segmento(
                total_float, 
                dias_overdue, 
                resumo['qtd_dividas'] or 0
            )
            segmento = ctx['segmento']

        # 3. Selecionar o template e formatar
        template = cls.TEMPLATES.get(segmento, cls.TEMPLATES['fallback'])
        mensagem = template.format(nome=primeiro_nome)

        return {
            'mensagem': mensagem,
            'segmento': segmento,
            'segmento_label': segmento.replace('_', ' ').title() if segmento else "Geral"
        }
