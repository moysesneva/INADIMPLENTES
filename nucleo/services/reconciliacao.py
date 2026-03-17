import csv
import io
from datetime import datetime
from django.utils import timezone
from django.db import transaction, IntegrityError
import hashlib
from decimal import Decimal
from ..models import Acordo, Parcela, PagamentoAcordo, ItemRetornoPendente, LoteRetornoPagamento, RegistroAuditoria

def calcular_hash_arquivo(file_obj):
    """
    Calcula o hash SHA256 de um arquivo para evitar importações duplicadas.
    """
    hasher = hashlib.sha256()
    # Se for um arquivo aberto, volta pro início
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    
    # Se for um Django UploadedFile ou FieldFile, usamos chunks()
    if hasattr(file_obj, 'chunks'):
        for chunk in file_obj.chunks():
            hasher.update(chunk)
    else:
        # Fallback para arquivos normais
        while True:
            chunk = file_obj.read(8192)
            if not chunk:
                break
            if isinstance(chunk, str):
                chunk = chunk.encode('utf-8')
            hasher.update(chunk)
            
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    return hasher.hexdigest()

def processar_lote_retorno(lote_id, usuario_id=None):
    """
    Processa um lote de retorno de pagamentos de forma atômica e segura.
    Cada linha do CSV é validada contra o ID do Acordo e o CPF do Devedor.
    """
    try:
        lote = LoteRetornoPagamento.objects.get(id=lote_id)
    except LoteRetornoPagamento.DoesNotExist:
        return False

    lote.status_processamento = 'PROCESSANDO'
    lote.save()

    sucessos = 0
    pendentes = 0
    falhas = 0

    try:
        with lote.arquivo.open('r') as f:
            content = f.read().decode('utf-8')
            # Suporta diversos delimitadores
            try:
                dialect = csv.Sniffer().sniff(content[:2048])
            except:
                dialect = 'excel' # Fallback
            
            reader = csv.DictReader(io.StringIO(content), dialect=dialect)
            
            linhas = list(reader)
            lote.qtd_linhas_total = len(linhas)
            lote.save()

            for idx, row in enumerate(linhas):
                try:
                    # Normalização de dados
                    raw_cpf = str(row.get('cpf', '')).strip().replace('.', '').replace('-', '')
                    raw_acordo_id = str(row.get('acordo_id', '')).strip()
                    raw_valor = str(row.get('valor', '')).strip().replace(',', '.')
                    raw_data = str(row.get('data', '')).strip()

                    if not raw_valor:
                        continue

                    try:
                        valor_importado = float(raw_valor)
                    except ValueError:
                        continue
                    
                    # Parsing de data
                    data_pgto = None
                    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                        try:
                            data_pgto = datetime.strptime(raw_data, fmt).date()
                            break
                        except:
                            continue
                    
                    if not data_pgto:
                        data_pgto = timezone.now().date()

                    # ID de Referência para Idempotência (Lote_Linha)
                    ref_externa = f"LOTE_{lote.id}_LINHA_{idx}"

                    # Evitar processamento duplicado da mesma linha (Idempotência)
                    if PagamentoAcordo.objects.filter(referencia_externa=ref_externa).exists():
                        continue

                    # ESTRATÉGIA DE MATCHING RIGOROSA (ID + CPF)
                    acordo = None
                    if raw_acordo_id.isdigit():
                        acordo = Acordo.objects.filter(id=int(raw_acordo_id), devedor__cpf=raw_cpf).first()

                    if acordo:
                        # REGRA DE INTEGRIDADE: Pagamento + Abate + Status Acordo devem ser atômicos
                        try:
                            with transaction.atomic():
                                # Lock do Acordo para serializar qualquer operação financeira sobre ele (Step 3)
                                acordo_lock = Acordo.objects.select_for_update().get(id=acordo.id)
                                
                                PagamentoAcordo.objects.create(
                                    acordo=acordo_lock,
                                    lote=lote,
                                    data_pagamento=data_pgto,
                                    valor_pago=valor_importado,
                                    meio_pagamento="Retorno Bancário",
                                    referencia_externa=ref_externa,
                                    operador=lote.operador
                                )

                                # Lógica de Abate em Cascata nas Parcelas (internamente usa select_for_update)
                                abater_valor_nas_parcelas(acordo_lock, valor_importado, data_pgto)
                                
                            sucessos += 1
                        except IntegrityError:
                            # Idempotência a nível de banco de dados (referencia_externa única)
                            # Se cair aqui, a linha já foi processada anteriormente em algum lote
                            continue
                        except Exception as e:
                            # Se a transação financeira falhar, registramos como pendência para não perder o dado
                            ItemRetornoPendente.objects.create(
                                lote=lote,
                                raw_cpf=raw_cpf,
                                raw_acordo_id=raw_acordo_id,
                                raw_valor=raw_valor,
                                raw_data=raw_data,
                                motivo_pendencia=f"Erro transacional ao aplicar baixa: {str(e)}"
                            )
                            pendentes += 1
                    else:
                        # Match falhou -> Pendência para revisão manual (Operação Única)
                        ItemRetornoPendente.objects.create(
                            lote=lote,
                            raw_cpf=raw_cpf,
                            raw_acordo_id=raw_acordo_id,
                            raw_valor=raw_valor,
                            raw_data=raw_data,
                            motivo_pendencia="Acordo não localizado ou CPF não corresponde ao ID informado."
                        )
                        pendentes += 1

                except Exception as e:
                    ItemRetornoPendente.objects.create(
                        lote=lote,
                        raw_cpf=row.get('cpf'),
                        raw_acordo_id=row.get('acordo_id'),
                        raw_valor=row.get('valor'),
                        raw_data=row.get('data'),
                        motivo_pendencia=f"Erro de processamento: {str(e)}"
                    )
                    falhas += 1
                    continue

    except Exception as e:
        lote.status_processamento = 'FALHA'
        lote.save()
        return False

    # Finalização do Lote
    lote.qtd_sucesso_auto = sucessos
    lote.qtd_pendentes_revisar = pendentes + falhas
    lote.status_processamento = 'AGUARDANDO_REVISAO' if (pendentes + falhas) > 0 else 'CONCLUIDO'
    lote.save()

    # Auditoria
    RegistroAuditoria.objects.create(
        usuario_id=usuario_id,
        acao='RETORNO_IMPORTADO',
        detalhes=f"Lote #{lote.id} processado. Sucessos: {sucessos}, Pendências: {pendentes+falhas}."
    )

    return True

def abater_valor_nas_parcelas(acordo, valor_recebido, data_pagamento):
    """
    Distribui o valor recebido entre as parcelas pendentes do acordo (fonte da verdade: detalhe_parcelas).
    Usa select_for_update() para garantir exclusividade na atualização (Step 3).
    Aplica travas de consistência financeira (Step 4).
    """
    # Converte para Decimal para segurança nas comparações e operações (Step 4)
    valor_recebido_dec = Decimal(str(valor_recebido))

    if valor_recebido_dec <= 0:
        raise ValueError("O valor do pagamento deve ser maior que zero.")

    if acordo.status == 'CANCELADO':
        raise ValueError("Não é permitido aplicar pagamentos em acordos cancelados.")

    # Bloqueia as parcelas específicas deste acordo para evitar double settlement concorrente
    parcelas = acordo.detalhe_parcelas.select_for_update().exclude(status='PAGO').order_by('vencimento')
    
    # Validação de teto financeiro: evita que o pagamento exceda a soma das parcelas em aberto (Step 4)
    total_pendente = sum([p.valor_previsto - (p.valor_pago or 0) for p in parcelas])
    
    if valor_recebido_dec > total_pendente:
        raise ValueError(f"O valor R$ {valor_recebido_dec} excede o saldo total devedor (R$ {total_pendente}).")

    valor_disponivel = valor_recebido_dec

    for parcela in parcelas:
        if valor_disponivel <= 0:
            break
        
        # Parcela usa valor_previsto no schema ativo
        valor_falta = parcela.valor_previsto - (parcela.valor_pago or 0)
        abate = min(valor_disponivel, valor_falta)
        
        parcela.valor_pago = (parcela.valor_pago or 0) + abate
        parcela.data_pagamento = data_pagamento
        valor_disponivel -= abate

        if parcela.valor_pago >= parcela.valor_previsto:
            parcela.status = 'PAGO'
        else:
            parcela.status = 'PARCIAL'
        
        parcela.save()

    # Atualizar status global do acordo (regra 5.4 do sistema ativo)
    acordo.atualizar_status_por_parcelas()

def conciliar_manualmente(item_pendente_id, acordo_id, usuario_id):
    """
    Vincula um item pendente a um acordo específico e processa o pagamento.
    """
    try:
        item = ItemRetornoPendente.objects.get(id=item_pendente_id, resolvido=False)
        acordo = Acordo.objects.get(id=acordo_id)
        
        with transaction.atomic():
            # Lock do Acordo para reconciliação manual segura
            acordo_lock = Acordo.objects.select_for_update().get(id=acordo_id)
            
            valor_pgto = float(str(item.raw_valor).replace(',', '.'))
            
            # Parsing de data simplificado
            data_pgto = timezone.now().date()
            try:
                data_pgto = datetime.strptime(item.raw_data, '%d/%m/%Y').date()
            except:
                pass

            # Cria registro de pagamento
            PagamentoAcordo.objects.create(
                acordo=acordo_lock,
                lote=item.lote,
                data_pagamento=data_pgto,
                valor_pago=valor_pgto,
                meio_pagamento="Reconciliação Manual",
                reconciliado_manualmente=True,
                referencia_externa=f"MANUAL_ITEM_{item.id}"
            )

            # Processa baixa
            abater_valor_nas_parcelas(acordo_lock, valor_pgto, data_pgto)

            # Marca item como resolvido
            item.resolvido = True
            item.acordo_vinculado_manual = acordo
            item.data_resolucao = timezone.now()
            item.operador_resolucao_id = usuario_id
            item.save()

            # Auditoria
            RegistroAuditoria.objects.create(
                usuario_id=usuario_id,
                acao='PAGAMENTO_MANUAL',
                detalhes=f"Item pendente do Lote #{item.lote.id} conciliado manualmente com Acordo #{acordo.id}."
            )
            
        return True
    except IntegrityError:
        # Duplicidade em reconciliação manual
        return False
    except Exception as e:
        return False
