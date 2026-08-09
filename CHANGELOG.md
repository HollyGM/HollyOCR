# Histórico de versões

Todas as mudanças relevantes do HollyOCR são registradas neste arquivo.

## 5.0.0 — 2026-08-08

### Adicionado

- Nova identidade HollyOCR e ícones para macOS, Windows e interface.
- Versionamento canônico com número de build.
- Metadados modernos de pacote e comandos `hollyocr`/`HollyOCR`.
- Testes de regressão para segurança de arquivos e Apple Vision.
- Documentação de compilação, segurança e contribuição.

### Alterado

- Pacote interno reorganizado como `hollyocr`.
- Interface redesenhada com identidade tecnológica e processamento local.
- Migração de `PyPDF2` para `pypdf` 6.
- Atualização das dependências com vulnerabilidades conhecidas.
- Limites coerentes para DPI, processos paralelos e limiar de OCR.

### Corrigido

- Imagens fornecidas pelo usuário não são mais excluídas por padrão.
- Exclusão temporária fica restrita à pasta temporária do sistema.
- Exceções dentro do silenciador do Apple Vision propagam corretamente.
- Medição de imagens continua funcionando com a API atual do `pypdf`.
- PDFs corrompidos são fechados corretamente após a análise, inclusive no Windows.
- Configurações são migradas e gravadas de forma atômica.

### Removido

- Identidade visual jurídica anterior.
- Módulos e documentação obsoletos de recursos de IA externa.
