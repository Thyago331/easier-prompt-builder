# easier-prompt-builder

Aplicativo desktop para construir prompts a partir de texto do usuário, estrutura de diretórios e conteúdo de arquivos selecionados.

Nome da janela e do executável: **easier-prompt-builder**.

## Visão geral

O app permite:
- Adicionar múltiplas pastas.
- Navegar por um file tree recursivo.
- Remover itens do tree sem afetar o disco.
- Selecionar arquivos para concatenação.
- Escrever texto livre.
- Gerar a saída final com três blocos e copiar para a área de transferência ou salvar em arquivo.

Tudo com **tkinter** e apenas **standard library**.

## Funcionalidades

- Adição de várias pastas como raízes.
- Treeview com expand/collapse sob demanda.
- Remoção de itens do tree apenas na visualização/estado interno.
- Lista de arquivos a concatenar com prevenção de duplicatas.
- Heurística de leitura de texto:
  - Abre como UTF-8 com `errors="replace"`.
  - Se contiver byte NUL ou taxa alta de substituições, trata como binário e ignora.
  - Respeita tamanho máximo configurável.
- Filtro de extensões configurável.
- Geração do file tree textual no estilo `tree` usando `├──`, `└──`, `│`.
- Concatenação final na ordem:
  1. **TEXTO DO USUÁRIO**
  2. **FILE TREE**
  3. **CONTEÚDO DE ARQUIVOS** (com cabeçalhos e separadores)
- Copiar resultado para a área de transferência.
- Salvar resultado em arquivo.
- Log com tempos, contagens e decisões.
- Botões desabilitados durante operações longas.

## Requisitos

- Python 3.8+ (tkinter incluído).
- Windows, macOS ou Linux.
- Sem bibliotecas externas.

## Como executar em modo desenvolvimento

```bash
python main.py
````

A janela **easier-prompt-builder** abrirá.

## Como gerar o `.exe` com PyInstaller (Windows)

1. Instalar PyInstaller:

   ```bash
   pip install pyinstaller
   ```
2. Gerar o executável:

   ```bash
   python -m PyInstaller --noconsole --onefile --name easier-prompt-builder --icon assets/app.ico --add-data "assets/app.ico;assets" --add-data "assets/app-16x16.png;assets" --add-data "assets/app-32x32.png;assets" main.py

   ```
3. O `.exe` ficará em `dist/easier-prompt-builder.exe`.

## Uso passo a passo

1. Clique em **Adicionar pasta…** e escolha uma pasta. Repita para várias pastas. Duplicatas/subpastas sobrepostas são ignoradas.
2. Expanda nós no tree. O carregamento é sob demanda.
3. Opcional: selecione nós e clique em **Remover selecionados** para excluí-los da visualização e do processamento. Nada é apagado do disco.
4. Edite as **Extensões permitidas** e o **Tamanho máx. (MB)** se necessário.
5. Escreva seu texto na área **Texto do usuário**.
6. Selecione arquivos ou diretórios no tree e clique em **Adicionar selecionados do tree**. Arquivos duplicados são evitados. Diretórios adicionam seus arquivos recursivamente respeitando as extensões permitidas.
7. Revise a lista **Arquivos a concatenar**.
8. Clique em:

   * **Gerar e copiar** para montar a saída e copiar para a área de transferência.
   * **Salvar em arquivo…** para montar a saída e escolher onde salvar.
9. O **Log** mostra tempos, contagens e ignorados (binários, muito grandes, removidos, etc.).

## Configurações

* **Extensões permitidas**: lista separada por vírgula. Padrão:

  ```
  .txt,.md,.py,.json,.csv,.yml,.yaml,.ini,.log,.xml,.html,.css,.js,.ts
  ```
* **Tamanho máx. (MB)**: padrão `2`. Arquivos maiores são ignorados e logados.

## Limitações

* Pré-visualização de conteúdo não é exibida. O conteúdo é incorporado apenas na geração final.
* Remoção de itens no tree não remove do disco.
* Links simbólicos não são resolvidos recursivamente em algumas plataformas.
* O app usa apenas UTF-8 com substituição. Outros encodings podem ter mais substituições.
* A lista de arquivos não oferece remoção individual. Use **Limpar lista** para reiniciar ou ajuste o tree removendo subdiretórios/arquivos antes de adicionar.

## Troubleshooting

* **Nada acontece ao gerar**: verifique o **Log**. Pode não haver pastas, arquivos ou texto.
* **Arquivo ignorado como binário**: pode conter bytes NUL ou muitas substituições. Ajuste a seleção.
* **Arquivo ignorado por tamanho**: aumente o **Tamanho máx. (MB)**.
* **Extensão não permitida**: inclua-a nas **Extensões permitidas**.
* **Permissão negada**: execute com permissões adequadas ou evite diretórios restritos.

## Licença

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Créditos e versão

* Autor: Thyago de Azevedo Ribeiro
* Versão: 1.0.0



