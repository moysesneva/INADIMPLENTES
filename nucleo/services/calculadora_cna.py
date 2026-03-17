from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from django.db.models import QuerySet
from ..models import RegraCobranca, Divida

class CalculadoraCNA:
    """
    Motor de cálculo em memória para negociações de dívidas.
    Transpõe a lógica da planilha de referência (Colunas 21-58) para o sistema.
    """
    
    MODALIDADES = {
        "DIRETA_CNA": "Cobrança Direta CNA",
        "SERASA": "Cobrança Serasa",
        "FEIRAO_SERASA": "Cobrança Feirão Serasa",
    }

    def __init__(self, dividas):
        """
        Inicia a calculadora com uma dívida ou lista de dívidas.
        """
        if isinstance(dividas, Divida):
            self.dividas = [dividas]
        elif isinstance(dividas, (list, QuerySet)):
            self.dividas = list(dividas)
        else:
            raise ValueError("Entrada deve ser uma instância de Divida ou uma lista de dívidas.")

        # Agregação de valores baseline
        self.valor_original_total = sum((d.valor_original or Decimal('0')) for d in self.dividas)
        self.valor_atual_total = sum((d.valor_atual or Decimal('0')) for d in self.dividas)
        
        # Encargos são a diferença entre o atual e o original
        self.encargos_totais = self.valor_atual_total - self.valor_original_total
        
        # Dias de atraso (usa a maior data de vencimento para determinar a regra)
        self.dias_atraso = self._calcular_dias_atraso()

    def _calcular_dias_atraso(self):
        vencimentos = [d.vencimento for d in self.dividas if d.vencimento]
        if not vencimentos:
            return 0
        menor_vencimento = min(vencimentos)
        delta = date.today() - menor_vencimento
        return max(0, delta.days)

    def _get_regra_aplicavel(self, modalidade):
        """
        Busca a melhor regra de cobrança ativa para a modalidade e tempo de atraso.
        Filtra pela regra onde dias_atraso >= dias_atraso_minimo, pegando a de maior gatilho.
        """
        return RegraCobranca.objects.filter(
            modalidade=modalidade, 
            ativa=True,
            dias_atraso_minimo__lte=self.dias_atraso
        ).order_by('-dias_atraso_minimo').first()

    def _formatar_resultado(self, modalidade, regra, valor_final, desconto_concedido):
        """
        Padroniza a saída para consumo pela UI e persistência futura no Acordo.
        """
        # Entrada mínima sugerida
        entrada_minima = (valor_final * (regra.percentual_entrada_minima / Decimal('100'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Cálculo de parcela sugerida (exemplo: parcelas máximas)
        parcelas_max = regra.parcelas_maximas
        saldo_restante = valor_final - entrada_minima
        if parcelas_max > 1:
            valor_parcela = (saldo_restante / (parcelas_max - 1)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            valor_parcela = Decimal('0.00')

        return {
            "modalidade_id": modalidade,
            "modalidade_label": self.MODALIDADES.get(modalidade),
            "valor_base": self.valor_atual_total,
            "valor_original": self.valor_original_total,
            "encargos_originais": self.encargos_totais,
            "desconto_concedido": desconto_concedido.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            "valor_final": valor_final.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            "entrada_minima": entrada_minima,
            "parcelas_maximas": parcelas_max,
            "valor_parcela_sugerida": valor_parcela,
            "texto_parcelamento": f"R$ {valor_parcela} x {parcelas_max - 1} Parcelas" if parcelas_max > 1 else "À Vista",
            "regra_snapshot": {
                "id": regra.id,
                "limite_desc": float(regra.limite_desconto_juros_multa),
                "entrada_min": float(regra.percentual_entrada_minima),
                "max_parc": regra.parcelas_maximas
            }
        }

    def calcular_direta_cna(self):
        regra = self._get_regra_aplicavel("DIRETA_CNA")
        if not regra:
            return None
        
        # Desconto aplicado apenas sobre os encargos
        desconto = self.encargos_totais * (regra.limite_desconto_juros_multa / Decimal('100'))
        valor_final = self.valor_atual_total - desconto
        
        return self._formatar_resultado("DIRETA_CNA", regra, valor_final, desconto)

    def calcular_serasa(self):
        regra = self._get_regra_aplicavel("SERASA")
        if not regra:
            return None
        
        desconto = self.encargos_totais * (regra.limite_desconto_juros_multa / Decimal('100'))
        valor_final = self.valor_atual_total - desconto
        
        return self._formatar_resultado("SERASA", regra, valor_final, desconto)

    def calcular_feirao_serasa(self):
        regra = self._get_regra_aplicavel("FEIRAO_SERASA")
        if not regra:
            return None
        
        desconto = self.encargos_totais * (regra.limite_desconto_juros_multa / Decimal('100'))
        valor_final = self.valor_atual_total - desconto
        
        return self._formatar_resultado("FEIRAO_SERASA", regra, valor_final, desconto)

    def calcular_todas_modalidades(self):
        return {
            "DIRETA_CNA": self.calcular_direta_cna(),
            "SERASA": self.calcular_serasa(),
            "FEIRAO_SERASA": self.calcular_feirao_serasa(),
        }
