from django import forms
from django.forms import inlineformset_factory
from .models import Documento, Anexo, Remetente, TipoDocumento, NivelPrioridade, User
from django.utils import timezone

# Este é o formulário principal para cadastrar um Documento
class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento  # Baseia este formulário no nosso modelo 'Documento'
        
        # Define quais campos do modelo 'Documento' queremos no formulário
        fields = [
            'remetente', 
            'interessados',
            'notificar_remetente',
            'tipo_documento', 
            'prioridade',
            'num_doc_origem', 
            'data_doc_origem',
            'observacoes_protocolo'
        ]
        
        widgets = {
            'interessados': forms.SelectMultiple(attrs={'class': 'form-control select2-multiple'}),
            'data_doc_origem': forms.DateInput(
                attrs={'type': 'date'} # Transforma o campo de data em um seletor de calendário HTML5
            ),
        }     

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_doc_origem'].initial = timezone.now().date()
        self.fields['tipo_documento'].queryset = TipoDocumento.objects.order_by('descricao')

class AnexoForm(forms.ModelForm):
    class Meta:
        model = Anexo # Baseia este formulário no modelo 'Anexo'
        
        # Define os campos que queremos (apenas o arquivo)
        fields = ['arquivo']
        # Adiciona um rótulo mais claro
        labels = {
            'arquivo': ''
        }
        widgets = {
            'arquivo': forms.ClearableFileInput(attrs={
                # Filtra os arquivos na janela do navegador
                'accept': '.pdf, .png, .jpg, .jpeg' 
            })
        }

class RemetenteForm(forms.ModelForm):
    class Meta:
        model = Remetente
        fields = ['tipo_remetente', 'nome_razao_social', 'cpf_cnpj', 'email', 'telefone']
        # Podemos adicionar widgets se quisermos estilizar algo especificamente aqui

class FinalizacaoForm(forms.ModelForm):
    class Meta:
        model = Documento
        # Vamos usar apenas o campo de observações de finalização
        fields = ['obs_finalizacao']
        widgets = {
            'obs_finalizacao': forms.Textarea(
                attrs={'rows': 4, 'placeholder': 'Registre a ação final (ex: envio de e-mail) e escolha o próximo passo para este processo...'}
            )
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Torna o campo obrigatório, pois o usuário DEVE registrar a finalização
        self.fields['obs_finalizacao'].required = True
        self.fields['obs_finalizacao'].label = ""

class DocumentoFilterForm(forms.Form):
    protocolo = forms.CharField(
        label='Número do Protocolo', 
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: 2025-10-21-001',
            'class': 'form-control' # Adicionado
        })
    )
    
    interessados = forms.ModelChoiceField(
        queryset=Remetente.objects.all().order_by('nome_razao_social'),
        required=False,
        label="Interessado",
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    
    status = forms.ChoiceField(
        label='Status do Documento',
        choices=[('', 'Todos os Status')] + Documento.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}) # Adicionado
    )

    data_inicio = forms.DateField(
        label='Recebido de',
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control' # Adicionado
        })
    )
    
    data_fim = forms.DateField(
        label='Recebido até',
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control' # Adicionado
        })
    )

    tipo_documento = forms.ModelChoiceField(
        queryset=TipoDocumento.objects.all().order_by('descricao'), # A-Z
        required=False,
        label="Tipo de Documento",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

class AnexoForm(forms.ModelForm):
    class Meta:
        model = Anexo
        fields = ('arquivo',)
        widgets = {
            'arquivo': forms.FileInput(attrs={
                'accept': 'image/*,application/pdf',
                'class': 'form-control'
            })
        }
    
    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if arquivo:
            # Validação de tipo MIME
            tipos_permitidos = [
                'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 
                'image/bmp', 'image/webp', 'application/pdf'
            ]
            
            # Verifica o tipo MIME do arquivo
            if hasattr(arquivo, 'content_type'):
                if arquivo.content_type not in tipos_permitidos:
                    raise forms.ValidationError(
                        'Apenas imagens (JPEG, PNG, GIF, BMP, WebP) e arquivos PDF são permitidos.'
                    )
            
            # Validação de extensão (segurança adicional)
            extensao = arquivo.name.split('.')[-1].lower()
            extensoes_permitidas = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'pdf']
            if extensao not in extensoes_permitidas:
                raise forms.ValidationError(
                    'Extensão de arquivo não permitida. Use: JPG, PNG, GIF, BMP, WebP ou PDF.'
                )
            
            # Validação de tamanho (10 MB máximo)
            if arquivo.size > 10 * 1024 * 1024:
                raise forms.ValidationError(
                    'O arquivo é muito grande. Tamanho máximo: 10 MB.'
                )
        
        return arquivo

AnexoFormSet = inlineformset_factory(
    Documento,  # Modelo Pai
    Anexo,      # Modelo Filho
    form=AnexoForm,  # Usa o form customizado com validação
    fields=('arquivo',),
    extra=1,    # Começa com apenas 1 campo
    can_delete=True  # Permite deletar antes de salvar
)

class PinForm(forms.Form):
    # Campo para o novo PIN
    novo_pin = forms.CharField(
        label="Novo PIN de 4 Dígitos",
        widget=forms.PasswordInput(attrs={'maxlength': '4', 'pattern': '[0-9]{4}', 'autocomplete': 'off'}),
        help_text="O PIN deve conter exatamente 4 números."
    )
    
    # Campo para confirmar o novo PIN
    confirmar_pin = forms.CharField(
        label="Confirmar Novo PIN",
        widget=forms.PasswordInput(attrs={'maxlength': '4', 'pattern': '[0-9]{4}', 'autocomplete': 'off'})
    )

    def clean(self):
        """ Validação personalizada para verificar se os PINs são iguais. """
        cleaned_data = super().clean()
        novo_pin = cleaned_data.get("novo_pin")
        confirmar_pin = cleaned_data.get("confirmar_pin")

        # Verifica se ambos os campos foram preenchidos
        if novo_pin and confirmar_pin:
            # Verifica se são números
            if not novo_pin.isdigit() or not confirmar_pin.isdigit():
                raise forms.ValidationError("O PIN deve conter apenas números.")
            
            # Verifica se têm 4 dígitos
            if len(novo_pin) != 4 or len(confirmar_pin) != 4:
                raise forms.ValidationError("O PIN deve ter exatamente 4 dígitos.")
            
            # Verifica se são iguais
            if novo_pin != confirmar_pin:
                raise forms.ValidationError("Os PINs digitados não são iguais. Tente novamente.")
        
        return cleaned_data
    
class DocumentoUpdateForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ['num_doc_origem', 'protocolo', 'tipo_documento', 'prioridade', 'interessados', 'observacoes_protocolo']
        widgets = {
            # Protocolo como Readonly (Apenas Leitura)
            'protocolo': forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control-plaintext fw-bold px-2'}),
            'num_doc_origem': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_documento': forms.Select(attrs={'class': 'form-select'}),
            'prioridade': forms.Select(attrs={'class': 'form-select'}),
            # O campo original de interessados ficará escondido, o JS cuidará dele
            'interessados': forms.SelectMultiple(attrs={'class': 'd-none', 'id': 'id_interessados_hidden'}),
            'observacoes_protocolo': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Garante que a lista de interessados venha ordenada de A-Z
        self.fields['interessados'].queryset = Remetente.objects.all().order_by('nome_razao_social')

AnexoUpdateFormSet = inlineformset_factory(
    Documento, Anexo,
    fields=('arquivo', 'tipo_anexo', 'ativo'),
    extra=1,           # Permite adicionar um novo campo vazio para novo upload
    can_delete=True,   # No template, trataremos isso como 'Inativar'
    widgets={
        'tipo_anexo': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        'arquivo': forms.FileInput(attrs={'class': 'form-control form-control-sm'}),
        'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    }
)