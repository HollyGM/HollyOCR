# Histórico de versões

Todas as mudanças relevantes do HollyOCR são registradas neste arquivo.

## 5.0.0 (build 2) — 2026-08-18

Correções decorrentes de uma auditoria de código interna. Sem mudanças de comportamento visíveis na interface.

### Corrigido

- A linha de comando (`hollyocr -i ... -o ...`, sem `--gui`) agora reaproveita um único pool de processos para todo o lote de arquivos, em vez de abrir e encerrar um pool novo a cada lote de páginas de OCR. Em documentos de milhares de páginas, isso evitava overhead real e, com o backend Apple Vision, o reaquecimento repetido do modelo a cada pool novo.
- A migração de configurações antigas não confia mais em um `user_settings.json` avulso na pasta atual de execução ou na pasta do script; só os locais oficiais e os nomes legados documentados são considerados.
- O instalador de dependências do Windows (`install_dependencies.ps1`) verifica o hash SHA-256 do Poppler antes de extraí-lo.

### Removido

- Interface CustomTkinter morta (`gui/modern_ctk/widgets.py`, `theme.py`, `scroll_patches.py`), inalcançável a partir do aplicativo em uso, e as dependências `customtkinter`/`tkinterdnd2` que só existiam para sustentá-la.

### Documentado

- README: o `HollyOCR.app` compilado usa apenas `pypdf` para extração nativa (PyMuPDF fica desativado por estabilidade dentro do binário do PyInstaller); `HOLLYOCR_ENABLE_PYMUPDF=1` reativa o PyMuPDF.

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
