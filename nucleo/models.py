from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import datetime
import uuid


MODALIDADE_CHOICES = [
    ("DIRETA_CNA", "Cobrança Direta CNA"),
    ("SERASA", "Cobrança Serasa"),
    ("FEIRAO_SERASA", "Cobrança Feirão Serasa"),
]


class Devedor(models.Model):
    nome = models.CharField(max_length=200)
    cpf = models.CharField(max_length=14, unique=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    celular = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Endereço
    logradouro = models.CharField(max_length=255, blank=True, null=True)
    numero = models.CharField(max_length=20, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    uf = models.CharField(max_length=2, blank=True, null=True)
    cep = models.CharField(max_length=10, blank=True, null=True)
    complemento = models.CharField(max_length=255, blank=True, null=True)
    
    # Portal do Devedor
    uuid_acesso = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    def __str__(self):
        return f"{self.nome} ({self.cpf})"



class RegraCobranca(models.Model):
    modalidade = models.CharField(
        max_length=30,
        choices=MODALIDADE_CHOICES
    )
    dias_atraso_minimo = models.IntegerField(
        default=0,
        help_text="Quantidade mínima de dias de atraso para esta regra"
    )
    limite_desconto_juros_multa = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentual máximo de desconto permitido nos encargos"
    )
    percentual_entrada_minima = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentual mínimo de entrada exigido"
    )
    parcelas_maximas = models.IntegerField()
    ativa = models.BooleanField(default=True)

    def __str__(self):
        return self.get_modalidade_display()


class Divida(models.Model):
    ESCOLA_CHOICES = [
        ("CNA VIVENDAS", "CNA VIVENDAS"),
        ("CNA ITANHANGÁ", "CNA ITANHANGÁ"),
    ]

    devedor = models.ForeignKey(
        Devedor,
        on_delete=models.CASCADE,
        related_name="dividas"
    )

    escola = models.CharField(
        max_length=50,
        choices=ESCOLA_CHOICES,
        default="CNA VIVENDAS"
    )

    categoria_financeiro = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )

    ano_divida = models.IntegerField(
        blank=True,
        null=True
    )

    parcela = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    vencimento = models.DateField(
        blank=True,
        null=True
    )

    valor_original = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True
    )

    valor_atual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True
    )

    modalidade_sugerida = models.CharField(
        max_length=30,
        choices=MODALIDADE_CHOICES,
        blank=True,
        null=True,
        help_text="Modalidade sugerida na importação (Colunas 21-40)"
    )

    def __str__(self):
        return f"{self.devedor.nome} - {self.parcela or 'Sem parcela'}"


class Acordo(models.Model):
    STATUS_CHOICES = [
        ("EM_NEGOCIACAO", "Em Negociação"),
        ("AGUARDANDO_PAGAMENTO", "Aguardando Pagamento"),
        ("PAGO", "Pago"),
        ("QUEBRADO", "Quebrado"),
        ("CANCELADO", "Cancelado"),
    ]

    devedor = models.ForeignKey(Devedor, on_delete=models.CASCADE)

    numero_acordo = models.IntegerField(
        unique=True,
        blank=True,
        null=True
    )

    data_acordo = models.DateTimeField(auto_now_add=True)

    valor_total = models.DecimalField(max_digits=12, decimal_places=2)
    entrada = models.DecimalField(max_digits=12, decimal_places=2)
    saldo = models.DecimalField(max_digits=12, decimal_places=2)
    parcelas = models.IntegerField()
    valor_parcela = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="AGUARDANDO_PAGAMENTO"
    )

    modalidade = models.CharField(
        max_length=30,
        choices=MODALIDADE_CHOICES,
        null=True,
        blank=True
    )

    valor_desconto_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    regra_snapshot_metadata = models.JSONField(
        null=True,
        blank=True,
        help_text="Cópia dos limites da RegraCobranca no momento da assinatura"
    )

    usuario_criador = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acordos_criados"
    )

    def save(self, *args, **kwargs):
        if not self.numero_acordo:
            ultimo = Acordo.objects.order_by("-numero_acordo").first()

            if ultimo and ultimo.numero_acordo:
                self.numero_acordo = ultimo.numero_acordo + 1
            else:
                self.numero_acordo = 3005

        super().save(*args, **kwargs)

    def gerar_parcelas(self):
        """
        Gera automaticamente os registros de Parcela vinculados a este Acordo.
        Parcela 0 = Entrada.
        Parcelas 1..N = Saldo remanescente parcelado.
        """
        # Parcela 0 (Entrada) - Vencimento na data do acordo
        Parcela.objects.create(
            acordo=self,
            numero=0,
            vencimento=self.data_acordo.date(),
            valor_previsto=self.entrada,
            status="PENDENTE"
        )

        if self.parcelas > 0:
            acumulado = Decimal("0.00")
            valor_p = self.valor_parcela

            for i in range(1, self.parcelas + 1):
                # Vencimento simplificado: +30 dias por parcela
                data_venc = self.data_acordo.date() + datetime.timedelta(days=30 * i)

                if i < self.parcelas:
                    valor_atual = valor_p
                else:
                    # Ajuste de centavos na última parcela para fechar o saldo
                    valor_atual = self.saldo - acumulado

                Parcela.objects.create(
                    acordo=self,
                    numero=i,
                    vencimento=data_venc,
                    valor_previsto=valor_atual,
                    status="PENDENTE"
                )
                acumulado += valor_atual

    def atualizar_status_por_parcelas(self):
        """
        Deriva o status do Acordo com base nas suas parcelas.
        Regra 5.4: 
        - Todas PAGO -> Acordo PAGO
        - Alguma Vencida e não PAGO -> Acordo QUEBRADO
        """
        if self.status == "CANCELADO":
            return
            
        parcelas = self.detalhe_parcelas.all()
        if not parcelas.exists():
            return

        hoje = datetime.date.today()
        todas_pagas = True
        alguma_atrasada = False

        for p in parcelas:
            if p.status != "PAGO":
                todas_pagas = False
                # Uma parcela é considerada atrasada se o vencimento passou e não está paga
                if p.vencimento < hoje:
                    alguma_atrasada = True
                    break
        
        novo_status = self.status
        if alguma_atrasada:
            novo_status = "QUEBRADO"
        elif todas_pagas:
            novo_status = "PAGO"
        elif self.status in ["QUEBRADO", "PAGO"]:
            # Se não está mais atrasada nem todas pagas, volta para o status padrão
            novo_status = "AGUARDANDO_PAGAMENTO"

        if novo_status != self.status:
            self.status = novo_status
            self.save(update_fields=['status'])

    def __str__(self):

        return f"Acordo #{self.numero_acordo} - {self.devedor.nome}"


class Parcela(models.Model):
    STATUS_PARCELA_CHOICES = [
        ("PENDENTE", "Pendente"),
        ("PAGO", "Pago"),
        ("ATRASADO", "Atrasado"),
    ]

    acordo = models.ForeignKey(
        Acordo,
        on_delete=models.CASCADE,
        related_name="detalhe_parcelas"
    )
    numero = models.IntegerField(help_text="Número da parcela (0 para entrada)")
    vencimento = models.DateField()
    valor_previsto = models.DecimalField(max_digits=12, decimal_places=2)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    data_pagamento = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_PARCELA_CHOICES,
        default="PENDENTE"
    )

    class Meta:
        ordering = ["numero"]

    def __str__(self):
        return f"Parcela {self.numero} - Acordo #{self.acordo.numero_acordo}"


# --- Motor de Notificações ---

class RegistroAuditoria(models.Model):
    ACAO_CHOICES = [
        ('LOGIN', 'Login no Sistema'),
        ('LOGOUT', 'Logout do Sistema'),
        ('ACORDO_CRIADO', 'Acordo Criado'),
        ('ACORDO_STATUS', 'Mudança Status Acordo'),
        ('NOTIFICACAO_ENVIADA', 'Notificação de Cobrança Enviada'),
        ('NOTIFICACAO_FALHA', 'Falha no Envio de Notificação'),
        ('BAIXA_PARCELA', 'Baixa de Parcela Manual'),
        ('RELATORIO_GERADO', 'Relatório Gerado/Exportado'),
        ('RETORNO_IMPORTADO', 'Lote de Pagamentos Importado'),
        ('PAGAMENTO_MANUAL', 'Reconciliação Manual de Pagamento'),
        ('ALERTA_GERADO', 'Alerta Financeiro Gerado pelo Sistema'),
        ('ALERTA_ATUALIZADO', 'Alerta Financeiro Atualizado'),
        ('ALERTA_RESOLVIDO', 'Alerta Financeiro Resolvido'),
        ('PORTAL_ACESSO', 'Acesso ao Portal do Devedor'),
    ]


    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    acao = models.CharField(max_length=50, choices=ACAO_CHOICES)
    detalhes = models.TextField()
    registro_id = models.CharField(max_length=50, null=True, blank=True, help_text="ID do objeto afetado (ex: Acordo ID)")

    def __str__(self):
        v_user = self.usuario.username if self.usuario else "Sistema"
        return f"[{self.data_hora.strftime('%d/%m/%Y %H:%M')}] {v_user} - {self.get_acao_display()}"


class RegraNotificacao(models.Model):
    CHOICES_CANAL = (('EMAIL', 'E-mail'), ('WHATSAPP', 'WhatsApp (Mock/Simulação)'))
    
    nome = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    ativo = models.BooleanField(default=True)
    canal = models.CharField(max_length=20, choices=CHOICES_CANAL, default='EMAIL')
    
    # Gatilhos baseados no Status do Acordo ativo
    status_alvo = models.CharField(max_length=30, choices=Acordo.STATUS_CHOICES)
    dias_gatilho = models.IntegerField(help_text="Dias após a criação do acordo para disparar")
    
    # Template
    assunto_email = models.CharField(max_length=200, null=True, blank=True)
    corpo_template = models.TextField(help_text="Placeholders: {nome}, {acordo_id}, {valor}, {escola}")

    def __str__(self):
        return self.nome


class HistoricoNotificacao(models.Model):
    STATUS_ENVIO = (
        ('PENDENTE', 'Pendente'),
        ('ENVIADO', 'Enviado'),
        ('ENTREGUE', 'Entregue'),
        ('LIDO', 'Lido'),
        ('FALHA', 'Falha'),
        ('SIMULADO', 'Simulado (Mock)'),
    )
    
    acordo = models.ForeignKey(Acordo, on_delete=models.CASCADE, related_name='notificacoes')
    regra = models.ForeignKey(RegraNotificacao, on_delete=models.PROTECT)
    alerta = models.ForeignKey('AlertaFinanceiro', on_delete=models.SET_NULL, null=True, blank=True, related_name='notificacoes_vinculadas')
    
    data_envio = models.DateTimeField(auto_now_add=True)
    data_entrega = models.DateTimeField(null=True, blank=True)
    data_leitura = models.DateTimeField(null=True, blank=True)
    
    mensagem_id_externo = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    canal = models.CharField(max_length=20)
    destinatario = models.CharField(max_length=255)
    conteudo_enviado = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_ENVIO)
    erro_log = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Notif #{self.id} - Acordo #{self.acordo.numero_acordo} ({self.status})"


class LoteRetornoPagamento(models.Model):
    STATUS_CHOICES = (
        ('PROCESSANDO', 'Processando'),
        ('CONCLUIDO', 'Concluido'),
        ('AGUARDANDO_REVISAO', 'Aguardando Revisão Manual'),
    )

    arquivo = models.FileField(upload_to='retornos_pagamento/')
    arquivo_hash = models.CharField(max_length=64, unique=True, null=True, blank=True, help_text="Hash SHA256 do arquivo para evitar duplicatas")
    data_importacao = models.DateTimeField(auto_now_add=True)
    operador = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, related_name='lotes_retorno')
    
    qtd_linhas_total = models.IntegerField(default=0)
    qtd_sucesso_auto = models.IntegerField(default=0)
    qtd_pendentes_revisar = models.IntegerField(default=0)
    qtd_falhas_fatais = models.IntegerField(default=0)
    
    status_processamento = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROCESSANDO')

    def __str__(self):
        return f"Lote #{self.id} - {self.data_importacao.strftime('%d/%m/%Y %H:%M')}"


class PagamentoAcordo(models.Model):
    acordo = models.ForeignKey(Acordo, on_delete=models.CASCADE, related_name='pagamentos_detalhados')
    lote = models.ForeignKey(LoteRetornoPagamento, on_delete=models.SET_NULL, null=True, blank=True, related_name='pagamentos_gerados')
    
    data_pagamento = models.DateField(db_index=True)
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2)
    meio_pagamento = models.CharField(max_length=50, blank=True, null=True)
    referencia_externa = models.CharField(max_length=100, blank=True, null=True, unique=True)
    
    reconciliado_manualmente = models.BooleanField(default=False)
    data_registro = models.DateTimeField(auto_now_add=True)

    operador = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagamentos_registrados"
    )

    def __str__(self):
        return f"Pagamento R$ {self.valor_pago} - Acordo #{self.acordo.id}"


class ItemRetornoPendente(models.Model):
    lote = models.ForeignKey(LoteRetornoPagamento, on_delete=models.CASCADE, related_name='itens_pendentes')
    
    raw_cpf = models.CharField(max_length=14, blank=True, null=True)
    raw_acordo_id = models.CharField(max_length=20, blank=True, null=True)
    raw_valor = models.CharField(max_length=50, blank=True, null=True)
    raw_data = models.CharField(max_length=50, blank=True, null=True)
    
    motivo_pendencia = models.TextField()
    resolvido = models.BooleanField(default=False)
    acordo_vinculado_manual = models.ForeignKey(Acordo, on_delete=models.SET_NULL, null=True, blank=True, related_name='itens_retorno_resolvidos')
    data_resolucao = models.DateTimeField(null=True, blank=True)
    operador_resolucao = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Pendente Lote #{self.lote.id} - CPF: {self.raw_cpf}"


class AlertaFinanceiro(models.Model):
    TIPO_CHOICES = [
        ('PARCELA_ATRASADA', 'Parcela Atrasada'),
        ('ACORDO_RISCO', 'Acordo em Risco (Atraso Significativo)'),
        ('QUEBRA_ACORDO', 'Quebra de Acordo Detectada'),
        ('RISCO_PROXIMO', 'Risco: Vencimento Próximo'),
    ]

    SEVERIDADE_CHOICES = [
        ('BAIXA', 'Baixa'),
        ('MEDIA', 'Média'),
        ('ALTA', 'Alta'),
    ]

    STATUS_CHOICES = [
        ('ABERTO', 'Aberto'),
        ('EM_TRATAMENTO', 'Em Tratamento (Lido/Em Contato)'),
        ('RESOLVIDO', 'Resolvido'),
        ('IGNORADO', 'Ignorado'),
    ]

    acordo = models.ForeignKey(Acordo, on_delete=models.CASCADE, related_name='alertas')
    parcela = models.ForeignKey(Parcela, on_delete=models.SET_NULL, null=True, blank=True, related_name='alertas')
    tipo_alerta = models.CharField(max_length=50, choices=TIPO_CHOICES)
    severidade = models.CharField(max_length=20, choices=SEVERIDADE_CHOICES, default='BAIXA')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ABERTO')
    
    data_criacao = models.DateTimeField(auto_now_add=True)
    descricao = models.TextField()
    usuario_responsavel = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    origem = models.CharField(max_length=20, default='SISTEMA')

    class Meta:
        verbose_name = "Alerta Financeiro"
        verbose_name_plural = "Alertas Financeiros"
        # Idempotency constraint: Only one open alert of a certain type per object
        # Note: In a real scenario, we might want to allow new alerts after resolution.
        # This index helps the service layer logic.

    def __str__(self):
        return f"[{self.severidade}] {self.get_tipo_alerta_display()} - {self.acordo}"


@receiver(post_save, sender=Acordo)
def criar_parcelas_pos_acordo(sender, instance, created, **kwargs):
    if created:
        instance.gerar_parcelas()