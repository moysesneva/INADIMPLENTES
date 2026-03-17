from django.contrib import admin
from .models import (
    Devedor, Divida, Acordo, RegraCobranca, Parcela, 
    RegistroAuditoria, RegraNotificacao, HistoricoNotificacao,
    LoteRetornoPagamento, PagamentoAcordo, ItemRetornoPendente,
    AlertaFinanceiro
)

@admin.register(AlertaFinanceiro)
class AlertaFinanceiroAdmin(admin.ModelAdmin):
    list_display = ("tipo_alerta", "acordo", "severidade", "status", "data_criacao")
    list_filter = ("tipo_alerta", "severidade", "status", "data_criacao")
    search_fields = ("acordo__numero_acordo", "descricao")
    readonly_fields = ("data_criacao",)

@admin.register(Devedor)
class DevedorAdmin(admin.ModelAdmin):
    list_display = ("nome", "cpf", "email")
    readonly_fields = ("uuid_acesso",)
    search_fields = ("nome", "cpf")


@admin.register(Divida)
class DividaAdmin(admin.ModelAdmin):
    list_display = ("devedor", "escola", "categoria_financeiro", "ano_divida", "valor_original", "valor_atual")


@admin.register(Acordo)
class AcordoAdmin(admin.ModelAdmin):
    list_display = ("id", "numero_acordo", "devedor", "valor_total", "parcelas", "status", "data_acordo")
    search_fields = ("id", "numero_acordo", "devedor__nome", "devedor__cpf")


@admin.register(RegraCobranca)
class RegraCobrancaAdmin(admin.ModelAdmin):
    list_display = (
        "modalidade",
        "dias_atraso_minimo",
        "limite_desconto_juros_multa",
        "percentual_entrada_minima",
        "parcelas_maximas",
        "ativa",
    )


@admin.register(Parcela)
class ParcelaAdmin(admin.ModelAdmin):
    list_display = ("acordo", "numero", "vencimento", "valor_previsto", "valor_pago", "status")
    list_filter = ("status", "vencimento")
    search_fields = ("acordo__numero_acordo", "acordo__devedor__nome")


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("data_hora", "usuario", "acao", "registro_id")
    list_filter = ("acao", "data_hora")
    readonly_fields = ("data_hora", "usuario", "acao", "detalhes", "registro_id")
    search_fields = ("detalhes", "registro_id")


@admin.register(RegraNotificacao)
class RegraNotificacaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "canal", "status_alvo", "dias_gatilho", "ativo")
    list_filter = ("canal", "status_alvo", "ativo")
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(HistoricoNotificacao)
class HistoricoNotificacaoAdmin(admin.ModelAdmin):
    list_display = ("data_envio", "acordo", "regra", "alerta", "canal", "status")
    list_filter = ("status", "canal", "data_envio", "data_entrega", "data_leitura")
    readonly_fields = ("data_envio", "data_entrega", "data_leitura", "acordo", "regra", "alerta", "canal", "destinatario", "conteudo_enviado", "status", "erro_log", "mensagem_id_externo")
    search_fields = ("acordo__numero_acordo", "destinatario", "mensagem_id_externo")


@admin.register(LoteRetornoPagamento)
class LoteRetornoPagamentoAdmin(admin.ModelAdmin):
    list_display = ("id", "data_importacao", "operador", "status_processamento", "qtd_linhas_total", "qtd_sucesso_auto")
    list_filter = ("status_processamento", "data_importacao")


@admin.register(PagamentoAcordo)
class PagamentoAcordoAdmin(admin.ModelAdmin):
    list_display = ("acordo", "data_pagamento", "valor_pago", "meio_pagamento", "reconciliado_manualmente")
    list_filter = ("data_pagamento", "meio_pagamento", "reconciliado_manualmente")
    search_fields = ("acordo__id", "acordo__numero_acordo", "referencia_externa")


@admin.register(ItemRetornoPendente)
class ItemRetornoPendenteAdmin(admin.ModelAdmin):
    list_display = ("lote", "raw_cpf", "raw_acordo_id", "raw_valor", "resolvido")
    list_filter = ("resolvido", "lote")
    search_fields = ("raw_cpf", "raw_acordo_id")