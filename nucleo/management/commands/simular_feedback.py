from django.core.management.base import BaseCommand
from django.utils import timezone
from nucleo.models import HistoricoNotificacao, AlertaFinanceiro
from nucleo.services.notificacao import atualizar_status_notificacao
import random

class Command(BaseCommand):
    help = 'Simula o feedback de entrega e leitura de notificações para validar o ciclo de vida da Fase G3'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Iniciando simulação de feedback de comunicação...'))
        
        # 1. Pegar notificações enviadas/simuladas que não têm feedback ainda
        pendentes = HistoricoNotificacao.objects.filter(status__in=['ENVIADO', 'SIMULADO'])
        
        if not pendentes.exists():
            self.stdout.write(self.style.WARNING('Nenhuma notificação pendente de feedback encontrada.'))
            return

        for notif in pendentes:
            # Sorteio: 70% chance de ser Entregue, 40% chance de ser Lido
            roll = random.random()
            
            if roll > 0.3: # Entregue
                atualizar_status_notificacao(notif.id, 'ENTREGUE')
                self.stdout.write(self.style.SUCCESS(f'Notif #{notif.id} marcada como ENTREGUE.'))
                
                # Segunda chance: Lido (se já foi entregue)
                if random.random() > 0.5:
                    atualizar_status_notificacao(notif.id, 'LIDO')
                    self.stdout.write(self.style.SUCCESS(f'Notif #{notif.id} marcada como LIDO -> Alerta atualizado para EM_TRATAMENTO.'))
            else:
                # 30% chance de falha mock
                atualizar_status_notificacao(notif.id, 'FALHA', erro="Simulação de erro na entrega (MOCK)")
                self.stdout.write(self.style.ERROR(f'Notif #{notif.id} marcada como FALHA.'))

        self.stdout.write(self.style.SUCCESS('Simulação de feedback concluída.'))
