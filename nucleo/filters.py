import django_filters
from .models import Devedor, Acordo

class DevedorFilter(django_filters.FilterSet):
    nome = django_filters.CharFilter(lookup_expr='icontains', label='Nome')
    cpf = django_filters.CharFilter(lookup_expr='icontains', label='CPF')
    cidade = django_filters.CharFilter(lookup_expr='icontains', label='Cidade')

    class Meta:
        model = Devedor
        fields = ['nome', 'cpf', 'cidade']

class AcordoFilter(django_filters.FilterSet):
    numero_acordo = django_filters.CharFilter(lookup_expr='icontains', label='Nº Acordo')
    status = django_filters.ChoiceFilter(choices=Acordo.STATUS_CHOICES, label='Status')
    data_inicio = django_filters.DateFilter(field_name='data_acordo', lookup_expr='gte', label='De')
    data_fim = django_filters.DateFilter(field_name='data_acordo', lookup_expr='lte', label='Até')
    devedor_nome = django_filters.CharFilter(field_name='devedor__nome', lookup_expr='icontains', label='Devedor')

    class Meta:
        model = Acordo
        fields = ['status', 'numero_acordo']
