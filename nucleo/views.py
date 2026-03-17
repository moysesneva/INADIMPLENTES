import datetime
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.db.models import Sum, Q, Count, F, DecimalField, ExpressionWrapper
from .models import (
    Devedor, Acordo, Divida, Parcela, RegistroAuditoria,
    LoteRetornoPagamento, ItemRetornoPendente, PagamentoAcordo,
    AlertaFinanceiro
)
from .services.calculadora_cna import CalculadoraCNA
from .filters import DevedorFilter, AcordoFilter
from .services import export, reconciliacao, estatisticas


@login_required
def home(request):
    busca = request.GET.get("busca", "").strip()
    devedores = Devedor.objects.annotate(
        total_divida=Sum("dividas__valor_atual")
    ).order_by("nome")

    if busca:
        devedores = devedores.filter(
            Q(nome__icontains=busca) | Q(cpf__icontains=busca)
        )

    return render(request, "nucleo/home.html", {
        "devedores": devedores,
        "busca": busca,
    })


@login_required
def devedor_detail(request, pk):
    devedor = get_object_or_404(Devedor, pk=pk)
    dividas = devedor.dividas.all().order_by("vencimento")
    acordos = Acordo.objects.filter(devedor=devedor).order_by("-data_acordo")

    total = dividas.aggregate(total=Sum("valor_atual"))["total"] or Decimal("0.00")
    
    # Validação segura da Fase 5.4: atualiza status conforme parcelas
    for acordo in acordos:
        acordo.atualizar_status_por_parcelas()

    # Simulação de modalidades para exibição na UI
    calculadora = CalculadoraCNA(dividas)
    simulacoes = calculadora.calcular_todas_modalidades()

    return render(request, "nucleo/devedor_detail.html", {
        "devedor": devedor,
        "dividas": dividas,
        "acordos": acordos,
        "total": total,
        "simulacoes": simulacoes,
    })


@login_required
def gerar_acordo(request, pk):
    devedor = get_object_or_404(Devedor, pk=pk)
    dividas = devedor.dividas.all().order_by("vencimento")
    
    total_bruto = dividas.aggregate(total=Sum("valor_atual"))["total"] or Decimal("0.00")

    modalidade_id = request.GET.get("modalidade", "").strip() or None
    entrada_str = request.GET.get("entrada", "0").replace(",", ".").strip()
    parcelas_str = request.GET.get("parcelas", "1").strip()

    # Se uma modalidade foi escolhida, o valor total do acordo muda
    simulacao = None
    valor_base_negociacao = total_bruto
    if modalidade_id:
        calculadora = CalculadoraCNA(dividas)
        simulacoes = calculadora.calcular_todas_modalidades()
        simulacao = simulacoes.get(modalidade_id)
        if simulacao:
            valor_base_negociacao = simulacao["valor_final"]

    try:
        entrada = Decimal(entrada_str)
    except:
        entrada = Decimal("0.00")

    try:
        parcelas = int(parcelas_str)
    except:
        parcelas = 1

    if parcelas < 1:
        parcelas = 1

    saldo = valor_base_negociacao - entrada
    if saldo < 0:
        saldo = Decimal("0.00")

    valor_parcela = saldo / parcelas if parcelas > 0 else saldo

    return render(request, "nucleo/acordo.html", {
        "devedor": devedor,
        "dividas": dividas,
        "total": valor_base_negociacao,
        "total_bruto": total_bruto,
        "entrada": entrada,
        "parcelas": parcelas,
        "valor_parcela": valor_parcela,
        "saldo": saldo,
        "modalidade_id": modalidade_id,
        "simulacao": simulacao,
    })


@login_required
def salvar_acordo(request, pk):
    devedor = get_object_or_404(Devedor, pk=pk)
    dividas = devedor.dividas.all().order_by("vencimento")
    total_bruto = dividas.aggregate(total=Sum("valor_atual"))["total"] or Decimal("0.00")

    if request.method != "POST":
        return redirect("gerar_acordo", pk=devedor.id)

    modalidade_id = request.POST.get("modalidade", "").strip() or None
    entrada_str = request.POST.get("entrada", "0").replace(",", ".").strip()
    parcelas_str = request.POST.get("parcelas", "1").strip()

    try:
        entrada = Decimal(entrada_str)
    except:
        entrada = Decimal("0.00")

    try:
        parcelas = int(parcelas_str)
    except:
        parcelas = 1

    # Recaptura do contexto da modalidade para snapshot imutável
    valor_total_negociado = total_bruto
    desconto_concedido = Decimal("0.00")
    regra_metadata = None

    if modalidade_id:
        calculadora = CalculadoraCNA(dividas)
        simulacao = calculadora.calcular_todas_modalidades().get(modalidade_id)
        if simulacao:
            valor_total_negociado = simulacao["valor_final"]
            desconto_concedido = simulacao["desconto_concedido"]
            regra_metadata = simulacao["regra_snapshot"]

    saldo = valor_total_negociado - entrada
    if saldo < 0:
        saldo = Decimal("0.00")

    valor_parcela = saldo / parcelas if parcelas > 0 else saldo

    Acordo.objects.create(
        devedor=devedor,
        valor_total=valor_total_negociado,
        entrada=entrada,
        saldo=saldo,
        parcelas=parcelas,
        valor_parcela=valor_parcela,
        status="AGUARDANDO_PAGAMENTO",
        modalidade=modalidade_id,
        valor_desconto_total=desconto_concedido,
        regra_snapshot_metadata=regra_metadata,
        usuario_criador=request.user
    )

    return redirect("devedor_detail", pk=devedor.id)


@login_required
def imprimir_acordo(request, pk):
    acordo = get_object_or_404(Acordo, pk=pk)
    return render(request, "nucleo/acordo_pdf.html", {
        "acordo": acordo,
        "devedor": acordo.devedor,
    })


@login_required
def devedor_list(request):
    devedores = Devedor.objects.all().order_by("nome")
    filtro = DevedorFilter(request.GET, queryset=devedores)
    return render(request, "nucleo/devedor_list.html", {
        "filter": filtro,
    })


@login_required
def acordo_list(request):
    acordos = Acordo.objects.select_related("devedor").order_by("-data_acordo")
    filtro = AcordoFilter(request.GET, queryset=acordos)
    return render(request, "nucleo/acordo_list.html", {
        "filter": filtro
    })


@login_required
def exportar_devedores(request):
    formato = request.GET.get("formato", "csv")
    devedores = Devedor.objects.all().order_by("nome")
    filtro = DevedorFilter(request.GET, queryset=devedores)
    
    # Registrar auditoria
    RegistroAuditoria.objects.create(
        usuario=request.user,
        acao='RELATORIO_GERADO',
        detalhes=f"Exportação de Devedores (Formato: {formato.upper()}). Filtros: {request.GET.urlencode()}"
    )

    if formato == "excel":
        return export.generate_excel_response(filtro.qs, "devedores")
    return export.generate_csv_response(filtro.qs, "devedores")


@login_required
def exportar_acordos(request):
    formato = request.GET.get("formato", "csv")
    acordos = Acordo.objects.select_related("devedor").order_by("-data_acordo")
    filtro = AcordoFilter(request.GET, queryset=acordos)
    
    # Registrar auditoria
    RegistroAuditoria.objects.create(
        usuario=request.user,
        acao='RELATORIO_GERADO',
        detalhes=f"Exportação de Acordos (Formato: {formato.upper()}). Filtros: {request.GET.urlencode()}"
    )

    if formato == "excel":
        return export.generate_excel_response(filtro.qs, "acordos")
    return export.generate_csv_response(filtro.qs, "acordos")


@login_required
def dashboard(request):
    hoje = datetime.date.today()
    kpis = estatisticas.EstatisticasService.obter_kpis_financeiros()

    # --- Totais gerais (contratos) ---
    total_dividas = Divida.objects.aggregate(total=Sum("valor_atual"))["total"] or Decimal("0.00")
    total_acordos = kpis['valor_acordado_total']
    total_entradas = Acordo.objects.aggregate(total=Sum("entrada"))["total"] or Decimal("0.00")

    # --- Contadores de acordos ---
    qtd_devedores = Devedor.objects.count()
    qtd_dividas = Divida.objects.count()
    qtd_acordos = Acordo.objects.count()

    status_map = kpis['status_map']
    qtd_aguardando = status_map.get("AGUARDANDO_PAGAMENTO", 0)
    qtd_pago = status_map.get("PAGO", 0)
    qtd_quebrado = status_map.get("QUEBRADO", 0)
    qtd_cancelado = Acordo.objects.filter(status="CANCELADO").count()
    qtd_em_negociacao = status_map.get("EM_NEGOCIACAO", 0)

    # --- Listas ---
    top_devedores = []
    top_devedores_qs = (
        Devedor.objects
        .annotate(total_valor=Sum("dividas__valor_atual"))
        .filter(total_valor__gt=0)
        .order_by("-total_valor")[:10]
    )
    for devedor in top_devedores_qs:
        top_devedores.append({
            "devedor": devedor,
            "total": devedor.total_valor,
        })

    ultimos_acordos = Acordo.objects.select_related("devedor").order_by("-data_acordo")[:10]
    
    kpis_gestao = estatisticas.EstatisticasService.obter_kpis_gestao()

    context = {
        "total_dividas": total_dividas,
        "total_acordos": total_acordos,
        "total_entradas": total_entradas,
        "qtd_devedores": qtd_devedores,
        "qtd_dividas": qtd_dividas,
        "qtd_acordos": qtd_acordos,
        "qtd_aguardando": qtd_aguardando,
        "qtd_pago": qtd_pago,
        "qtd_quebrado": qtd_quebrado,
        "qtd_cancelado": qtd_cancelado,
        "qtd_em_negociacao": qtd_em_negociacao,
        "valor_pago": kpis['total_recuperado'],
        "valor_em_aberto": total_acordos - kpis['total_recuperado'],
        "qtd_parcelas_pagas": kpis['parcelas_pagas'],
        "qtd_parcelas_pendentes": kpis['parcelas_pendentes'],
        "qtd_parcelas_atrasadas": kpis['parcelas_atrasadas'],
        "top_devedores": top_devedores,
        "ultimos_acordos": ultimos_acordos,
        "kpis": kpis,
        "kpis_gestao": kpis_gestao,
        "alertas_recentes": AlertaFinanceiro.objects.filter(status='ABERTO').select_related('acordo__devedor').order_by('-severidade', '-data_criacao')[:10],
        "total_alertas_abertos": AlertaFinanceiro.objects.filter(status='ABERTO').count(),
    }

    return render(request, "nucleo/dashboard.html", context)


@login_required
def alterar_status_acordo(request, pk):
    acordo = get_object_or_404(Acordo, pk=pk)
    if request.method == "POST":
        novo_status = request.POST.get("status")
        status_validos = ["EM_NEGOCIACAO", "AGUARDANDO_PAGAMENTO", "PAGO", "QUEBRADO", "CANCELADO"]
        if novo_status in status_validos:
            acordo.status = novo_status
            acordo.save()
    return redirect("devedor_detail", pk=acordo.devedor.id)


@login_required
def baixar_parcela(request, pk):
    parcela = get_object_or_404(Parcela, pk=pk)
    
    if request.method == "POST":
        valor_pago_str = request.POST.get("valor_pago", "0").replace(",", ".").strip()
        data_pagamento = request.POST.get("data_pagamento")
        
        try:
            valor_pago = Decimal(valor_pago_str)
        except:
            valor_pago = Decimal("0.00")
            
        if valor_pago <= 0:
            return redirect("devedor_detail", pk=parcela.acordo.devedor.id)

        try:
            with transaction.atomic():
                # Bloqueia a parcela específica (Step 3)
                p_lock = Parcela.objects.select_for_update().get(pk=pk)
                
                # Regras Financeiras (Step 4)
                if valor_pago > p_lock.valor_previsto:
                    # Auditoria de tentativa inválida
                    RegistroAuditoria.objects.create(
                        usuario=request.user,
                        acao='BAIXA_PARCELA',
                        detalhes=f"Tentativa de pagamento excessiva REJEITADA: R$ {valor_pago} para parcela de R$ {p_lock.valor_previsto}. Acordo #{p_lock.acordo.id}"
                    )
                    return redirect("devedor_detail", pk=p_lock.acordo.devedor.id)

                p_lock.valor_pago = valor_pago
                p_lock.data_pagamento = data_pagamento
                
                # Regra de negócio: apenas liquidação total marca como PAGO
                if valor_pago >= p_lock.valor_previsto:
                    p_lock.status = "PAGO"
                else:
                    p_lock.status = "PENDENTE"
                    
                p_lock.save()

                # IDENTIDADE REFORÇADA (Step 6): Chave determinística sem dependência de timestamp
                # Formato: MANUAL_P{id}_V{valor}_D{data}_U{user}
                ref_manual = f"MANUAL_P{p_lock.id}_V{valor_pago}_D{data_pagamento}_U{request.user.id}"
                
                try:
                    PagamentoAcordo.objects.create(
                        acordo=p_lock.acordo,
                        data_pagamento=data_pagamento or datetime.date.today(),
                        valor_pago=valor_pago,
                        meio_pagamento="Baixa Manual (Operador)",
                        referencia_externa=ref_manual,
                        reconciliado_manualmente=True,
                        operador=request.user
                    )
                except IntegrityError:
                    # Se a chave colidir, significa que este exato pagamento já foi registrado (Step 6)
                    RegistroAuditoria.objects.create(
                        usuario=request.user,
                        acao='PAGAMENTO_MANUAL',
                        detalhes=f"Bloqueio de duplicidade: Pagamento idêntico já registrado para Parcela {p_lock.id}. Ref: {ref_manual}"
                    )
                    # Forçamos o rollback da transação atômica levantando o erro para o bloco externo
                    raise IntegrityError("Pagamento duplicado detectado.")
                
                # Fase 5.4: Atualiza status do acordo pai imediatamente após a baixa
                p_lock.acordo.atualizar_status_por_parcelas()

                # Auditoria de sucesso
                RegistroAuditoria.objects.create(
                    usuario=request.user,
                    acao='BAIXA_PARCELA',
                    detalhes=f"Baixa manual realizada: Parcela {p_lock.numero} do Acordo #{p_lock.acordo.id}. Valor: R$ {valor_pago}"
                )
        except Exception as e:
            # Captura erros gerais, incluindo o raise IntegrityError interno
            pass
            
    return redirect("devedor_detail", pk=parcela.acordo.devedor.id)


@login_required
def financeiro_dashboard(request):
    lotes = LoteRetornoPagamento.objects.all().order_by("-data_importacao")
    return render(request, "nucleo/financeiro/dashboard.html", {"lotes": lotes})


@login_required
def importar_retorno(request):
    if request.method == "POST" and request.FILES.get("arquivo"):
        arquivo = request.FILES["arquivo"]
        
        # Cálculo de hash para evitar duplicidade de arquivo (Step 2)
        arquivo_hash = reconciliacao.calcular_hash_arquivo(arquivo)
        
        lote_existente = LoteRetornoPagamento.objects.filter(arquivo_hash=arquivo_hash).first()
        if lote_existente:
            # Se o arquivo já foi importado, redireciona para a revisão do lote existente
            return redirect("revisar_lote", pk=lote_existente.id)

        lote = LoteRetornoPagamento.objects.create(
            arquivo=arquivo,
            arquivo_hash=arquivo_hash,
            operador=request.user
        )
        # Processamento síncrono para simplicidade na Fase 1
        reconciliacao.processar_lote_retorno(lote.id, request.user.id)
        return redirect("revisar_lote", pk=lote.id)
    return render(request, "nucleo/financeiro/importar.html")


@login_required
def revisar_lote(request, pk):
    lote = get_object_or_404(LoteRetornoPagamento, pk=pk)
    pendencias = lote.itens_pendentes.filter(resolvido=False)
    pagamentos = lote.pagamentos_gerados.all().select_related("acordo__devedor")
    return render(request, "nucleo/financeiro/revisar_lote.html", {
        "lote": lote,
        "pendencias": pendencias,
        "pagamentos": pagamentos,
    })


@login_required
def resolver_pendencia(request, pk):
    item = get_object_or_404(ItemRetornoPendente, pk=pk)
    if request.method == "POST":
        acordo_id = request.POST.get("acordo_id")
        if reconciliacao.conciliar_manualmente(item.id, acordo_id, request.user.id):
            return redirect("revisar_lote", pk=item.lote.id)
    return redirect("revisar_lote", pk=item.lote.id)


def portal_devedor(request, token):
    """
    Portal de auto-serviço do devedor acessado via link seguro (Token UUID).
    """
    devedor = get_object_or_404(Devedor, uuid_acesso=token)
    acordos = Acordo.objects.filter(devedor=devedor).exclude(status='CANCELADO').order_by("-data_acordo")
    
    # Log de acesso para auditoria
    RegistroAuditoria.objects.create(
        acao='PORTAL_ACESSO',
        detalhes=f"Portal acessado pelo devedor {devedor.nome} (IP: {request.META.get('REMOTE_ADDR')})",
        registro_id=str(devedor.pk)
    )

    # Engajamento: Move alertas ABERTOS para EM_TRATAMENTO ao acessar o portal
    alertas_vinculados = AlertaFinanceiro.objects.filter(acordo__devedor=devedor, status='ABERTO')
    if alertas_vinculados.exists():
        for alerta in alertas_vinculados:
            alerta.status = 'EM_TRATAMENTO'
            alerta.save()
            
            RegistroAuditoria.objects.create(
                acao='ALERTA_ATUALIZADO',
                detalhes=f"Alerta #{alerta.id} movido para EM_TRATAMENTO (Acesso ao Portal)",
                registro_id=str(alerta.acordo.id)
            )

    return render(request, "nucleo/portal_devedor.html", {
        "devedor": devedor,
        "acordos": acordos,
    })