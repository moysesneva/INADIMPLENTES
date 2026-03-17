from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper, Avg
from django.db.models.functions import Cast
from django.utils import timezone
from decimal import Decimal
import datetime
from ..models import Acordo, Parcela, PagamentoAcordo, Devedor, Divida
from django.contrib.auth.models import User

class EstatisticasService:
    @staticmethod
    def obter_kpis_financeiros():
        """
        Calcula os KPIs financeiros core baseados no livro razão (PagamentoAcordo).
        Métricas focadas em montantes financeiros liquidados.
        """
        hoje = timezone.now().date()
        primeiro_dia_mes = hoje.replace(day=1)
        
        # 1. Recuperação Total Bancária: sum(PagamentoAcordo.valor_pago)
        # Fonte: Todos os registros validados no ledger central de pagamentos.
        total_recuperado = PagamentoAcordo.objects.aggregate(
            total=Sum('valor_pago')
        )['total'] or Decimal('0.00')

        # 2. Recuperação Mês Atual: sum(PagamentoAcordo.valor_pago) onde data >= dia 01
        recuperado_mes_atual = PagamentoAcordo.objects.filter(
            data_pagamento__gte=primeiro_dia_mes
        ).aggregate(
            total=Sum('valor_pago')
        )['total'] or Decimal('0.00')

        # 3. Recuperação Janela 30 Dias: sum(PagamentoAcordo.valor_pago) nos últimos 30 dias corridos
        trinta_dias_atras = hoje - datetime.timedelta(days=30)
        recuperado_30_dias = PagamentoAcordo.objects.filter(
            data_pagamento__gte=trinta_dias_atras
        ).aggregate(
            total=Sum('valor_pago')
        )['total'] or Decimal('0.00')

        # 4. Divisão por Origem (Automação vs Operação):
        # - Lotes: Importações de arquivos bancários processadas automaticamente.
        # - Manuais: Baixas realizadas diretamente pelo operador na interface.
        pagamentos_lote = PagamentoAcordo.objects.filter(
            lote__isnull=False
        ).aggregate(total=Sum('valor_pago'))['total'] or Decimal('0.00')
        
        pagamentos_manuais = PagamentoAcordo.objects.filter(
            lote__isnull=True
        ).aggregate(total=Sum('valor_pago'))['total'] or Decimal('0.00')

        # 5. Saúde da Carteira e Taxa de Recuperação Global:
        # Fórmula: (Valor Já Pago) / (Valor Total Previsto nos Acordos Ativos)
        # Notas: Excluímos CANCELADOS para evitar poluição da métrica de performance.
        acordos_ativos = Acordo.objects.exclude(status='CANCELADO')
        valor_acordado_total = acordos_ativos.aggregate(total=Sum('valor_total'))['total'] or Decimal('0.00')
        
        taxa_recuperacao = Decimal('0.00')
        if valor_acordado_total > 0:
            taxa_recuperacao = (total_recuperado / valor_acordado_total) * 100

        # 6. Status de Parcelas: Contagens brutas para visão de pipeline de recebimento.
        parcelas_pagas = Parcela.objects.filter(status='PAGO').count()
        parcelas_atrasadas = Parcela.objects.filter(
            status__in=['PENDENTE', 'ATRASADO'], 
            vencimento__lt=hoje
        ).count()
        parcelas_pendentes = Parcela.objects.filter(
            status='PENDENTE', 
            vencimento__gte=hoje
        ).count()

        # 7. Proporção de Estados de Acordo:
        proporcao_status = acordos_ativos.values('status').annotate(total=Count('id'))
        status_map = {item['status']: item['total'] for item in proporcao_status}

        return {
            'total_recuperado': total_recuperado,
            'recuperado_mes_atual': recuperado_mes_atual,
            'recuperado_30_dias': recuperado_30_dias,
            'taxa_recuperacao': taxa_recuperacao,
            'pagamentos_lote': pagamentos_lote,
            'pagamentos_manuais': pagamentos_manuais,
            'parcelas_pagas': parcelas_pagas,
            'parcelas_atrasadas': parcelas_atrasadas,
            'parcelas_pendentes': parcelas_pendentes,
            'status_map': status_map,
            'valor_acordado_total': valor_acordado_total,
        }

    @staticmethod
    def obter_kpis_gestao():
        """
        Calcula KPIs de performance e gestão focados em eficiência operacional.
        Diferencia explicitamente Criadores de Acordo (Negociadores) de Processadores (Operadores).
        """
        # 1. Performance de Arrecadação por Operador (Processamento de Caixa)
        # Fórmula: sum(valor_pago) onde PagamentoAcordo.operador == user
        # Objetivo: Medir quem está processando o caixa ou realizando as baixas manuais.
        ranking_recuperacao_operador = User.objects.annotate(
            valor_recuperado=Sum('pagamentos_registrados__valor_pago'),
            qtd_pagamentos=Count('pagamentos_registrados')
        ).filter(valor_recuperado__gt=0).order_by('-valor_recuperado')[:5]

        # 2. Eficiência de Conversão por Criador de Acordo (Negociação)
        # Fórmula: count(Acordos PAGO do user) / count(Total Acordos Criados pelo user)
        # Objetivo: Medir a qualidade da negociação (acordos que realmente chegam à quitação).
        conversao_negociadores = User.objects.annotate(
            total_criados=Count('acordos_criados'),
            total_pagos=Count('acordos_criados', filter=Q(acordos_criados__status='PAGO'))
        ).filter(total_criados__gt=0).order_by('-total_pagos')[:5]

        # 3. Velocidade de Recebimento (Tempo Médio até Primeiro Pagamento)
        # Fórmula: avg(primeiro_pagamento.data - acordo.data_acordo) em dias.
        # Objetivo: Medir o tempo de resposta entre a fechamento do acordo e a primeira entrada financeira.
        acordos_com_pagamento = Acordo.objects.annotate(
            data_primeiro_pgto=Min('pagamentos_detalhados__data_pagamento')
        ).filter(data_primeiro_pgto__isnull=False)
        
        media_tempo_pagamento = acordos_com_pagamento.annotate(
            diferenca=ExpressionWrapper(
                F('data_primeiro_pgto') - Cast(F('data_acordo'), output_field=models.DateField()),
                output_field=models.DurationField()
            )
        ).aggregate(media=Avg('diferenca'))['media']

        tempo_medio_dias = media_tempo_pagamento.days if media_tempo_pagamento else 0

        # 4. Taxa de Conversão Global da Operação
        # Fórmula: count(Total Acordos PAGO) / count(Total Acordos Não Cancelados)
        total_acordos = Acordo.objects.exclude(status='CANCELADO').count()
        total_acordos_pagos = Acordo.objects.filter(status='PAGO').count()
        conversao_global = (total_acordos_pagos / total_acordos * 100) if total_acordos > 0 else 0

        return {
            'ranking_operadores': ranking_recuperacao_operador,
            'conversao_operadores': conversao_negociadores,
            'tempo_medio_pagamento': tempo_medio_dias,
            'conversao_global': conversao_global,
        }

from django.db.models import Min
from django.db import models
