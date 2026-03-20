from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper, Avg, Min
from django.db.models.functions import Cast
from django.utils import timezone
from decimal import Decimal
import datetime
import math
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

    @staticmethod
    def calcular_score_e_segmento(total_open_amount, dias_overdue, total_debts):
        """
        Lógica centralizada para cálculo de score, segmentação e estratégia.
        Inclui agora Categoria de Atenção e Prioridade Operacional (Fase G).
        """
        # 1. Cálculo do Score Base (Fórmula Logarítmica Original)
        # Score = (log10(Valor+1)*10) + (Dias*0.2) + (Dividas*2)
        score_base = (math.log10(total_open_amount + 1) * 10) + \
                     (dias_overdue * 0.2) + \
                     (total_debts * 2)

        # 2. Pesos para dominância (diagnóstico)
        v_weight = math.log10(total_open_amount + 1) * 10
        a_weight = dias_overdue * 0.2
        r_weight = total_debts * 2

        # 3. Limiares Críticos e Diagnóstico
        thresholds_met = 0
        reasons = []
        if total_open_amount > 5000: 
            thresholds_met += 1
            reasons.append({'id': 'valor', 'label': 'Valor Elevado', 'icon': '💰'})
        if dias_overdue > 90: 
            thresholds_met += 1
            reasons.append({'id': 'atraso', 'label': 'Atraso Crítico', 'icon': '⏳'})
        if total_debts >= 3: 
            thresholds_met += 1
            reasons.append({'id': 'recorrencia', 'label': 'Recorrência', 'icon': '🔄'})

        # 4. Segmentação de Risco
        if thresholds_met >= 2:
            segmento = "misto"
            segmento_label = "Misto"
            estrategia = "Foco em Conciliação Total / Abordagem de Alta Prioridade (360º)"
        else:
            weights = [
                (v_weight, "alto_valor", "Alto Valor", "Priorizar Negociação Direta / Desconto Agressivo à Vista"),
                (a_weight, "atraso_critico", "Atraso Crítico", "Ação Urgente / Reforçar Prazos e Restrições de Crédito"),
                (r_weight, "recorrencia", "Recorrência", "Monitoramento Constante / Quebra de Hábito de Atraso")
            ]
            _, segmento, segmento_label, estrategia = max(weights, key=lambda x: x[0])

        # 5. Categoria de Atenção e Bônus de Prioridade (Fase G)
        # Regras explícitas de atenção operacional
        atencao_categoria = "Acompanhamento Recomendado"
        atencao_bonus = 0
        proximo_passo = "Monitorar evolução do débito e aguardar janela de contato."

        if score_base > 80 or dias_overdue > 180:
            atencao_categoria = "Atenção Imediata"
            atencao_bonus = 20
            proximo_passo = "Priorizar contato telefônico hoje. Risco crítico de perda/inadimplência prolongada."
        elif segmento == "misto" or thresholds_met >= 2:
            atencao_categoria = "Caso Complexo"
            atencao_bonus = 15
            proximo_passo = "Avaliar composição da dívida. Possível necessidade de suporte de supervisão para fechar."
        elif total_open_amount > 5000 and dias_overdue < 60:
            atencao_categoria = "Negociação Prioritária"
            atencao_bonus = 10
            proximo_passo = "Oferecer condições agressivas para liquidação rápida (Ticket alto em estágio inicial)."
        elif total_debts >= 3:
            atencao_categoria = "Recorrência Crítica"
            atencao_bonus = 5
            proximo_passo = "Verificar histórico de promessas antes de conceder novos prazos."

        prioridade_operacional = score_base + atencao_bonus

        return {
            'score': round(score_base, 2),
            'segmento': segmento,
            'segmento_label': segmento_label,
            'estrategia': estrategia,
            'reasons': reasons,
            'atencao_categoria': atencao_categoria,
            'atencao_bonus': atencao_bonus,
            'proximo_passo': proximo_passo,
            'prioridade_operacional': round(prioridade_operacional, 2)
        }

    @staticmethod
    def obter_ranking_inadimplencia(limite_critico=10):
        """
        Gera os rankings de inadimplência para auxílio operacional.
        1. Top por Valor Aberto
        2. Top por Idade de Atraso (mais antigo)
        3. Ranking Crítico (Score Combinado - Nova Fórmula Logarítmica)
        
        Formula:
        Score = (log10(total_open_amount + 1) * 10) + (days_overdue * 0.2) + (total_debts * 2)
        """
        hoje = timezone.now().date()

        # 1. Top Devedores por Valor Aberto
        top_valor = Devedor.objects.annotate(
            total_aberto=Sum('dividas__valor_atual'),
            qtd_dividas=Count('dividas')
        ).filter(total_aberto__gt=0).order_by('-total_aberto')[:10]

        # 2. Top Devedores por Idade de Atraso
        top_atraso = Devedor.objects.annotate(
            vencimento_mais_antigo=Min('dividas__vencimento', filter=Q(dividas__vencimento__lt=hoje))
        ).filter(vencimento_mais_antigo__isnull=False).order_by('vencimento_mais_antigo')[:10]

        for d in top_atraso:
            d.dias_atraso = (hoje - d.vencimento_mais_antigo).days

        # 3. Ranking de Inadimplência Crítica (Fórmula de Produção)
        # Processamos em Python para permitir a escala logarítmica complexa
        candidatos = Devedor.objects.annotate(
            total_aberto=Sum('dividas__valor_atual'),
            qtd_dividas=Count('dividas'),
            vencimento_mais_antigo=Min('dividas__vencimento', filter=Q(dividas__vencimento__lt=hoje))
        ).filter(total_aberto__gt=0)

        ranking_critico = []
        for d in candidatos:
            dias_overdue = (hoje - d.vencimento_mais_antigo).days if d.vencimento_mais_antigo else 0
            total_open_amount = float(d.total_aberto or 0)
            total_debts = d.qtd_dividas or 0

            ctx = EstatisticasService.calcular_score_e_segmento(total_open_amount, dias_overdue, total_debts)
            
            ranking_critico.append({
                'devedor': d,
                'total_aberto': d.total_aberto,
                'qtd_dividas': total_debts,
                'dias_atraso': dias_overdue,
                'vencimento_mais_antigo': d.vencimento_mais_antigo,
                **ctx
            })

        # Ordenação Descendente por Score
        ranking_critico = sorted(ranking_critico, key=lambda x: x['score'], reverse=True)[:limite_critico]

        return {
            'top_valor': top_valor,
            'top_atraso': top_atraso,
            'ranking_critico': ranking_critico
        }

    @staticmethod
    def obter_prioridade_do_dia(limite=10):
        """
        Gera a fila de Prioridade do Dia (Fase G).
        Ordenada pela Prioridade Operacional (Score + Bônus de Atenção).
        """
        hoje = timezone.now().date()
        
        # 1. Candidatos: Devedores com saldo em aberto
        candidatos = Devedor.objects.annotate(
            total_aberto=Sum('dividas__valor_atual'),
            qtd_dividas=Count('dividas'),
            vencimento_mais_antigo=Min('dividas__vencimento', filter=Q(dividas__vencimento__lt=hoje))
        ).filter(total_aberto__gt=0)

        fila_operacional = []
        for d in candidatos:
            dias_overdue = (hoje - d.vencimento_mais_antigo).days if d.vencimento_mais_antigo else 0
            total_open_amount = float(d.total_aberto or 0)
            total_debts = d.qtd_dividas or 0

            # 2. Calcular Inteligência Operacional
            ctx = EstatisticasService.calcular_score_e_segmento(total_open_amount, dias_overdue, total_debts)
            
            fila_operacional.append({
                'devedor': d,
                'total_aberto': d.total_aberto,
                'qtd_dividas': total_debts,
                'dias_atraso': dias_overdue,
                **ctx
            })

        # 3. Ordenação por Prioridade Operacional (Descendente)
        fila_operacional = sorted(fila_operacional, key=lambda x: x['prioridade_operacional'], reverse=True)[:limite]

        return fila_operacional
from django.db import models
