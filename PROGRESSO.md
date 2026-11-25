# Migração do PEGA

## Etapa 1 — Auditoria e testes

A auditoria de 25/11/2026 cobriu os módulos de importação, armazenamento, fatores e cálculo, as rotas FastAPI, o HTML, o CSS, o JavaScript e os arquivos de configuração Docker. O frontend já consulta a saúde da API e envia planilhas. O botão de processamento aguarda a integração da Etapa 2. O CSS contém regras sobrepostas para o vídeo principal, registradas para revisão durante a integração visual.

- A importação reutiliza os limites de ano da API de cálculo, de 1900 a 9999. Arquivos XLSX inválidos recebem uma mensagem de erro de leitura e HTTP 400.
- O cálculo reutiliza a lista de campos obrigatórios da importação, valida o total de consumo e protege a soma de consumos inteiros contra estouro de int64. A API verifica o acesso novamente antes de gravar o cálculo, trata a indisponibilidade do inventário durante a execução e deixou de imprimir parâmetros de diagnóstico.
- Os caminhos dos recursos estáticos são resolvidos a partir do código. A pasta de armazenamento é criada na primeira gravação e conserva o caminho relativo existente.
- A suíte usa inventários sintéticos e armazenamento temporário. Ela cobre os três formatos, validação e limite de upload, rotas, oito combustíveis, escolha explícita de SOx e Cu, aviso sobre Pb, isolamento por sessão, expiração, exclusão e persistência dos quatro arquivos de cálculo.
- A regressão sintética de biomassa cobre 505 atividades e fontes, 24 poluentes e 12.120 emissões. Ela verifica PM2.5 a 133 g/GJ e BC usando diretamente a fração 0,033, inclusive por atividade.
- A execução inicial com pandas 3.1.1 apontou uma descontinuação em `reset_index(inplace=True)`. A importação passou a usar o retorno de `reset_index`. A suíte usa httpx2 para acompanhar o TestClient atual do Starlette.

### Contagem da base científica

Dois leitores, pandas e o módulo `csv` da biblioteca padrão, confirmaram 40.814 linhas de dados e 17 colunas no CSV, 39.756 linhas após remover duplicatas integrais e 2.169 registros Tier 1 com região vazia e código de setor preenchido. A reconciliação com a contagem de 1.939 está na Etapa 2 abaixo.

### Resultados e reprodução local

- Windows com Python 3.13.7. Os 10 testes passaram em 8,191 s.
- Docker com Python 3.11.18. Os 10 testes passaram em 5,965 s durante a construção da imagem local `pega-auditoria-local`. O Docker Desktop recusou a montagem direta da pasta do disco D:, então a construção usou uma cópia do código, da base científica, dos recursos públicos e dos testes. O contêiner da aplicação e o volume de pesquisa ficaram fora da auditoria.
- A verificação de sintaxe do JavaScript com Node.js passou.
- No cenário de biomassa, o consumo sintético de 632.260 GJ produziu 84.090.580 g de PM2.5 e 2.774.989,14 g de BC.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check frontend/script.js
```

No VS Code, selecione `.venv/Scripts/python.exe` em **Python: Select Interpreter** para usar as dependências locais. A lista de diagnósticos ativos do editor e o interpretador selecionado na interface não estavam disponíveis para inspeção.

### Pendências

- Confirmar cientificamente a unidade e a magnitude do consumo da planilha original de biomassa. Os dados sintéticos validam o cálculo, e a verificação do arquivo original segue pendente.
- Antes da publicação, validar a implantação HTTPS com `COOKIE_SECURE=true` e os limites de tamanho e recursos no ponto de entrada. O limite atual de 50 MB é aplicado ao arquivo após o recebimento multipart. Arquivos XLSX comprimidos e cálculos com muitas atividades ainda podem exigir recursos desproporcionais.

## Etapa 2 — Integração funcional

### Reconciliação dos fatores Tier 1

A auditoria leu o objeto retornado por `pega::ef(returnfdb=TRUE)` do pacote **0.9.8 instalado** no R e comparou com o CSV usando `read.csv(colClasses = "character", na.strings = NULL)`. A cópia do código-fonte em `D:/pega` declara a versão 0.9.4. O R/Shiny local seleciona `is.na(region)` no cálculo, seguido dos filtros de setor, combustível e `type`.

| Seleção com tipo exato e código preenchido | Fatores | Setor 1.A.1.a |
| --- | ---: | ---: |
| R 0.9.8, `is.na(region)` | 1.939 | 149 |
| R 0.9.8, `region == ""` com NA excluído | 230 | 0 |
| R 0.9.8, união dos dois grupos | 2.169 | 149 |
| CSV, `region == ""` | 2.169 | 149 |

Os 230 fatores adicionais são de fonte EMEP. Para o tipo exato `Tier 1 Emission Factor`, os códigos de setor estão preenchidos. A coluna `region` dos fatores Tier 1 não contém marcadores literais `NA` nem campos formados só por espaços. A remoção de duplicatas integrais reduz de 40.814 para 39.756 linhas tanto no objeto R quanto no CSV. Cada grupo Tier 1 da tabela conserva sua contagem após essa deduplicação.

A exportação com `na=""` representa o NA e a string vazia pelo mesmo valor. O leitor Python mantém esse campo como string vazia, por isso o filtro inclui os dois grupos. O CSV atual não contém informação suficiente para refazer globalmente o filtro `is.na(region)`. Antes de ampliar o cálculo para outros setores, gere uma nova exportação da versão aprovada com um marcador explícito e livre de colisões para NA, ou use um formato que preserve o tipo nulo. Compare fatores, referências e identificadores antes de trocar a base.

No setor 1.A.1.a, os 149 registros pertencem todos ao grupo de NA do R. As 17 colunas coincidiram, tratando os NA textuais como vazios e comparando as colunas numéricas com tolerância de `1e-14`. Esse resultado permite avançar com os oito combustíveis atuais. O CSV, o filtro global e as equações foram preservados.

### Aplicação

- A interface conecta a importação aos setores suportados, usa os pares de ano e combustível realmente presentes na planilha e exibe o nome mapeado pelo backend. A análise mostra fatores automáticos, exige escolhas explícitas para referências ambíguas e apresenta os fatores indisponíveis.
- Os resultados incluem resumo tabular, gráfico de barras em escala linear em gramas, prévia por atividade, fatores usados e histórico de execuções. A aba do navegador lembra o último inventário e restaura o histórico ao recarregar enquanto a sessão for válida.
- Listagem, consulta e download são autorizados pelo cookie da sessão e retornam `Cache-Control: no-store`. Somente os quatro artefatos previstos são oferecidos para download. O cálculo é publicado no histórico após a gravação dos metadados. A exclusão manual remove todas as execuções do inventário.
- HTML, CSS e JavaScript reaproveitam a identidade visual e os recursos existentes. O teste de navegador usa um servidor local temporário e dados sintéticos.

### Resultados da validação

- Os 11 testes de API passaram no Windows com Python 3.13.7 e no Docker com Python 3.11.18. O teste adicional verificou listagem, consulta, download dos quatro arquivos, bloqueio para outra sessão e inutilização dos links depois de excluir o inventário.
- O teste Chrome/Playwright passou com a API servida por Uvicorn em loopback. Ele cobriu planilha inválida e válida, seleção dos anos e combustíveis, mapeamento de biomassa, escolha de SOx, aviso de Pb, três cálculos, tabela e gráfico, download, bloqueio em outra sessão, recuperação do histórico após recarregar, exibição a 390 px e exclusão.
- A sintaxe do JavaScript foi verificada com `node --check`. A imagem de auditoria foi construída localmente. O contêiner da aplicação e o volume de pesquisa ficaram fora da validação.

### Executar e testar no Windows

Use o ambiente virtual e as dependências da Etapa 1. Para abrir a versão atualizada numa porta independente do contêiner existente:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8001
```

Abra http://127.0.0.1:8001 para usar a aplicação ou http://127.0.0.1:8001/docs para consultar a API. Execute os testes de API e a verificação do JavaScript a partir da raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check frontend/script.js
```

Para repetir o fluxo no Chrome instalado, com Node.js disponível:

```powershell
npm.cmd install --prefix .venv/pega-browser playwright-core --no-audit --no-fund --no-package-lock
$env:PEGA_PLAYWRIGHT_MODULE = (Resolve-Path '.venv/pega-browser/node_modules/playwright-core').Path
$env:PEGA_BROWSER_EXECUTABLE = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
.\.venv\Scripts\python.exe -m tests.browser_smoke
```

A Etapa 2 foi aprovada após a execução no Docker e a conferência visual.

## Etapa 3 — Especiação química

O perfil `perfil_complexo` de `D:/APP_PEGA/R/calculos.R` fornece a nomenclatura, as frações e as massas moleculares. A transformação reproduz `emissão da espécie = emissão do poluente de origem × fração`, em gramas. A massa molecular (g/mol) é metadado. O perfil não traz referência bibliográfica específica, por isso os derivados registram o caminho lógico e o nome do perfil. As referências dos fatores de emissão são preservadas em cada registro. O tratamento de BC permanece o da versão Python já aprovada.

| Grupo | Espécies no R | Soma das frações | Parcela da massa original que fica como saldo |
| --- | ---: | ---: | ---: |
| PM2.5 | 16 | 0,9943 | 0,57% |
| SOx | 2 | 1 | 0% |
| NOx | 2 | 1 | 0% |
| NMVOC | 25 | 0,999129131 | 0,0870869% |

Os saldos são calculados por grupo disponível e reportados em gramas. As frações são preservadas tal como no R. PSO4 de PM2.5 e de SOx permanece separado pelo poluente de origem. Os poluentes fora do perfil passam para o arquivo derivado com suas emissões originais. Os registros mantêm identificador, coordenadas, atividade e fator original. O cálculo base permanece disponível. Uma nova solicitação para o mesmo cálculo reutiliza o derivado, que herda a autorização e a expiração do inventário. Grupos ausentes no cálculo têm o balanço marcado como indisponível.

O indicador de etapas mostra importação, configuração, emissões, especiação química, distribuição temporal, distribuição espacial e exportação. As etapas temporal e espacial são marcadas como indisponíveis. A Etapa 4 aguarda aprovação.

### Área central de Resultados

A barra de navegação principal dá acesso a Resultados. O processamento leva à mesma área, sempre vinculada à execução selecionada no histórico. A implementação avança conforme os módulos produzam resultados reais.

- **Visão geral.** Mostra ano, setor, combustível, fontes, poluentes, registros, consumo, resumo do processamento e avisos científicos. A especiação pode ser executada a partir da visão geral.
- **Tabelas.** Disponibiliza emissões por poluente, prévia por fonte, fatores e referências, balanço e resultados da especiação. A consulta completa por fonte, filtros, pesquisa, downloads de recortes e as tabelas de distribuição temporal são incrementos planejados.
- **Imagens e gráficos.** O gráfico de emissões totais está disponível. Planeja-se selecionar tipo de visualização, poluente ou espécie, unidade e escala linear ou logarítmica quando aplicável. A imagem selecionada deverá oferecer prévia, ampliação, download individual em PNG, PDF ou SVG, PNG em 300 ou 600 DPI e download em lote em ZIP. Gerar sob demanda, armazenar temporariamente em área privada e reutilizar imagens da mesma execução e configuração. A geração em lote ocorrerá a pedido.
- **Arquivos.** Centraliza os CSV e JSON já gerados. A seleção individual e a reunião de arquivos em um conjunto serão ampliadas com os produtores de NetCDF, imagens científicas, relatórios e ZIP. A autorização de downloads e coleções deve ser verificada no servidor a cada solicitação.

### Visualização científica planejada

- **Mapas por poluente ou espécie.** Estilos interativo e de publicação com fundo branco. Usar contorno do Brasil e limites estaduais, fontes nas coordenadas reais, paletas Plasma e Viridis ou equivalentes e magnitude por cor e, opcionalmente, por tamanho. Incluir barra de cor com unidade, latitude, longitude, grade, norte, escala cartográfica geograficamente correta, título com poluente, setor, combustível e ano, emissão total e quantidade de fontes. Documentar origem e licença dos dados geográficos. Permitir escala linear e logarítmica quando aplicável.
- **Perfis temporais por poluente ou espécie.** Perfil horário de 24 horas, semanal, combinado de 168 horas, mapa de calor de dias versus horas, distribuição anual quando aplicável e emissões totais por período. Permitir g, kg e t. Distinguir perfil relativo, estimativa por período e total anual. Validar a conservação da massa anual e o calendário do método. Perfis estimados devem ser identificados como estimativas.
- **Gráficos gerais.** Planejar escalas, seleção de unidade, ordenação por magnitude, informações interativas, exportação de alta resolução e formatação científica. Tratar zeros e nulos explicitamente, em especial na escala logarítmica. Avaliar Matplotlib, GeoPandas, Cartopy e Plotly conforme os módulos, evitando dependências antecipadas.

### Validação da Etapa 3

- As 45 linhas do perfil Python foram comparadas individualmente com uma extração do bloco original do R. Os nomes, frações e massas moleculares, inclusive as ausentes, coincidiram. O teste de regressão guarda o hash do perfil extraído, de modo que o Docker não precise do R para detectar divergências.
- Os 13 testes passaram no Windows com Python 3.13.7 e no Docker com Python 3.11.18. Incluem os testes das etapas anteriores e cobrem os quatro grupos, saldos de massa, preservação do cálculo base, coordenadas e referências, persistência, autorização, downloads e exclusão.
- O fluxo de navegador passou no Chrome, com dados sintéticos, incluindo especiação, abas, histórico, download e exclusão. A validação Docker usou uma imagem local de auditoria. O volume de pesquisa ficou fora dos testes.

Permanecem abertas a confirmação da unidade e magnitude do consumo real, a nova exportação Tier 1 antes de ampliar setores e a validação de segurança de produção. Para executar a versão atualizada, use o comando Uvicorn da seção anterior.

## Etapa 4 — Distribuição temporal

A Etapa 3 foi aprovada. O código de referência é `APP_PEGA/R/calculos.R`, nos blocos `perfil_semanal_ind`, `perfil_horario_ind` e `dt_temporal`. A migração preserva os 24 pesos horários, a normalização horária pela soma dos pesos brutos, os sete pesos semanais (domingo a sexta 0,1428 e sábado 0,1432) e a equação `massa alocada = massa da base × peso semanal × peso horário normalizado`. R confirma que as somas horária normalizada, semanal e combinada são 1. A soma horária bruta também é 1 em precisão decimal.

Os pesos são adimensionais. O perfil de 24 horas e o de sete dias representam distribuições marginais. Aplicar os 168 pesos à base reparte toda a massa daquela base em intervalos de um padrão relativo sem datas. O resultado em g, kg ou t é massa modelada por intervalo, não uma taxa (g/h) nem uma medição. Uma semana real ou representativa exige uma massa semanal definida por metodologia própria. Não se deve atribuir a massa anual inteira a essa semana.

A execução seleciona uma base por vez, original ou especiada. Na base especiada, as espécies ficam identificadas por origem, poluentes fora do perfil mantêm a massa e os saldos de especiação são carregados apenas como informação de auditoria, sem redistribuição. Ano, setor, combustível, configuração, poluentes, espécies, fonte e coordenadas são preservados nos metadados e/ou no CSV. Os resultados originais permanecem disponíveis.

O backend armazena metadados, perfis e resumos privados por cálculo e por base. O download CSV expande uma linha de origem em 168 linhas por vez, sem criar um arquivo intermediário com todas as combinações. A aba Visão geral executa o processamento, Tabelas apresenta perfis e massas e Imagens e gráficos gera somente a visualização selecionada. SVG e PNG usam fundo branco; PNG usa 2.400 ou 4.800 pixels de largura (300 ou 600 DPI quando impresso a 8 polegadas). O PDF usa a opção de salvar em PDF do diálogo de impressão do navegador. Os perfis e o CSV estão na aba Arquivos.

Validação: os 14 testes automatizados passaram no Windows (Python 3.13.7) e no Docker (Python 3.11.18). O teste Chrome passou para as quatro visualizações, exportações SVG e PNG, geração PDF pelo navegador e fluxo de resultados. Os testes usam dados sintéticos, armazenamento temporário e imagens de auditoria separadas do contêiner da aplicação. Permanecem as pendências de consumo real, exportação Tier 1 para outros setores e segurança de produção.

### Proposta separada para projeção anual (pendente de aprovação)

Para obter uma estimativa de calendário com 8.760 ou 8.784 horas, a proposta é definir uma convenção temporal explícita (UTC ou horário local fixo, a aprovar), enumerar as horas reais da convenção para o ano e atribuir a cada data/hora seu produto de pesos. Dividir cada produto pela soma dos produtos ao longo de todo o calendário, incluindo 29 de fevereiro quando aplicável, e multiplicar pela massa anual de cada série. Isso garante massa anual conservada mesmo com contagens diferentes de cada dia da semana. Quaisquer horários locais com horário de verão exigem tratamento explícito de horas ausentes ou repetidas. Uma semana datada seria extraída como subconjunto dessa série e uma semana representativa exigiria definição própria. Taxas, se necessárias, seriam calculadas separadamente, dividindo a massa pela duração do intervalo. A proposta não foi implementada por constituir uma extensão metodológica em relação ao R.

## Etapa 5 — Distribuição espacial e mapas científicos

A Etapa 4 foi aprovada. A projeção anual com calendário, as convenções temporais e as unidades WRF-Chem ficam para a Etapa 6.

### Metodologia e domínio

O original em `APP_PEGA/R/processamento.R` obtém as células do `wrfinput_d01` com `eixport::wrf_grid`, transforma os pontos de EPSG:4326 ao CRS da grade e aplica `sf::st_intersects`. Soma a massa por célula, poluente e intervalo do perfil. Depois converte para unidades WRF usando uma área fixa de 3 × 3 km no código. `mapas.R` representa a média por célula nesse estágio já convertido. A resolução espacial da grade vem do domínio. A hipótese de área fixa e a classificação das unidades por espécie precisam ser verificadas na Etapa 6, inclusive a espécie PSI, ausente da lista particulada do R.

O Python mantém pontos e agregação como resultados distintos. Sem grade, disponibiliza fontes nas suas coordenadas. Com uma coleção de polígonos com `properties.id_grid` e EPSG explícito, transforma os pontos e soma a massa em gramas por série e célula. O usuário pode fornecer a geometria previamente extraída do domínio WRF. A ingestão direta de `wrfinput`/NetCDF fica para a Etapa 6. A grade tem limite operacional de 15 MB e 25.000 células. Cada execução seleciona a base original ou especiada. O CSV preserva ID, coordenadas, altitude, fator e referência, e a série conserva o par poluente de origem e espécie.

O balanço contabiliza massa mapeada, fora da grade, com coordenada inválida e em interseção ambígua. Ao contrário de expandir um ponto com múltiplas interseções como o join do R, a implementação sinaliza essa massa e deixa sua alocação pendente. Assim evita atribuição a múltiplas células sem uma regra científica aprovada. Os saldos da especiação seguem como auditoria. O mapa exibe massas de emissão, sem estimar concentrações. O cenário sintético comparado ao R/`sf` confirmou 266.000 g no domínio e 133.000 g fora.

### Cartografia, mapas e dependências

A base pública local é a [Malha das Unidades da Federação de 2024 do IBGE](https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2024/Brasil/), escala de trabalho 1:250.000, referência original SIRGAS 2000 (EPSG:4674). A GeoJSON inclui as 27 UFs. Para apresentação nacional, a versão derivada foi simplificada em EPSG:5880 com tolerância de 1.200 m e convertida para EPSG:4326. A simplificação é usada apenas para desenho e não entra na interseção da grade. A [nota técnica e legal de 2024](https://www.ibge.gov.br/biblioteca/visualizacao/livros/liv102169.pdf) descreve licença compatível com CC BY 4.0 e exige atribuição ao IBGE; os mapas identificam a adaptação e a edição da fonte.

Matplotlib renderiza mapas de fundo branco e exporta PNG 300/600 DPI, PDF e SVG. Shapely fornece operações e índice espacial, e PyProj transforma os CRS e calcula a distância geodésica local da barra de escala no elipsoide WGS84. O mapa científico usa eixos geográficos em graus, norte verdadeiro, escala local de distância e limites estaduais. A visualização interativa usa SVG local e JavaScript nativo, com zoom, deslocamento e consulta da fonte. O navegador não carrega mosaicos de terceiros. GeoPandas, Cartopy e Plotly foram avaliados como alternativas e dispensados nesta etapa.

Na área Resultados, a Visão geral executa o processamento; Tabelas mostra a prévia das fontes e células; Imagens e gráficos permite selecionar tipo, série, unidade, escala, paleta, idioma, tamanho dos pontos e DPI, além de ampliar a imagem; Arquivos centraliza CSV, JSON, GeoJSON e mapas. Zeros ficam em cinza em escala logarítmica e coordenadas inválidas permanecem no CSV e no balanço.

O processamento lê o CSV linha a linha, mantém acumuladores por série e célula e limita a prévia tabular a 100 linhas por série. A prévia gráfica tem 100 DPI. A exportação renderiza uma imagem por vez e reaproveita o cache privado por cálculo, grade, série, parâmetros e versão cartográfica. Um ZIP em lote é viável como tarefa sequencial com limites de tamanho, quantidade e tempo; permanece como evolução, sem controle de lote nesta interface.

### Validação e desempenho

- Os 16 testes automatizados passaram no Windows com Python 3.13.7 e no Docker com Python 3.11.18. Cobrem interseção, reprojeção, massa dentro e fora da grade, coordenadas inválidas, separação das bases, conversão de unidades, exportação PNG/PDF/SVG, reutilização de artefatos e isolamento.
- O fluxo completo passou no Chrome com dados sintéticos, incluindo os mapas pontual, em grade e interativo, seletores de paleta e escala, consulta da fonte, zoom e interface cartográfica ativa em 390 px.
- A agregação sintética de 20.000 linhas demorou 1,24 s e atingiu um pico de 7,49 MiB de alocações rastreadas pelo Python. A medição não inclui toda a memória nativa nem representa um ensaio de produção.
- Nos exemplos com oito fontes, o PNG de pontos (600 DPI) levou 1,69 s e o de grade (300 DPI) 0,57 s. As solicitações com cache levaram 0,015 s e 0,009 s, respectivamente. Conferiram-se dimensões, DPI e aparência dos dois arquivos.

### Executar e avaliar

Na raiz do projeto, atualize as dependências, inicie a aplicação e abra http://127.0.0.1:8001:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8001
```

Rode os testes e regenere os exemplos sintéticos com:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tests.exemplos_espaciais
```

Os dois exemplos de PM2.5 estão em `exemplos/`. As coordenadas usadas no cenário são geográficas; os IDs, consumos, emissões e células são sintéticos. O teste Chrome segue o procedimento da Etapa 2. Continuam pendentes a confirmação do consumo real, a exportação Tier 1 para novos setores e a segurança da implantação pública. A Etapa 6 aguarda aprovação.

## Etapa 5.1 — Inteligência geográfica e aprimoramento dos mapas científicos

A Etapa 5 foi aprovada. Esta etapa acrescenta uma classificação territorial às bases de emissões existentes. A atribuição de fontes a células da grade, a especiação e os cálculos de emissão continuam seguindo suas metodologias aprovadas.

### Cartografia efetivamente utilizada

Os sete arquivos originais estão em `data/geospatial/` e foram preservados. A leitura com R/`sf` confirmou 27 UFs, CRS SIRGAS 2000 (EPSG:4674), cinco códigos regionais e os atributos `CD_UF`, `NM_UF`, `SIGLA_UF`, `CD_REGIAO`, `NM_REGIAO`, `SIGLA_RG` e `AREA_KM2`. A extensão observada foi aproximadamente 74° O a 29° O e 34° S a 5° N. A edição territorial é 2025, independentemente do ano do inventário.

A malha foi transformada para EPSG:4326 com GDAL/`sf` e exportada em GeoJSONSeq com nove casas decimais. As 27 feições eram válidas na leitura geográfica com `sf`; o GEOS encontrou duas geometrias inválidas no derivado. Foram reparadas com `make_valid`, retendo apenas os componentes poligonais. A cobertura e as geometrias resultantes passaram nas verificações de validade. O derivado detalhado foi armazenado em WKB hexadecimal dentro de JSONL compactado, sem simplificação, e é usado para classificação e mapas científicos.

Para o navegador, a cobertura foi projetada para EPSG:5880, simplificada de forma conjunta com `coverage_simplify` (tolerância de 1.600 m no algoritmo) e transformada de volta para EPSG:4326. A cobertura simplificada passou novamente na validação topológica. As cinco regiões foram unidas a partir dessa mesma cobertura. O derivado simplificado conserva os 27 códigos e atributos. Seu tamanho é cerca de 1,12 MB; o detalhado compactado tem cerca de 18,03 MB. Para reproduzir os derivados, exporte com `sf::st_write(sf::st_transform(malha, 4326), ..., driver="GeoJSONSeq", layer_options="COORDINATE_PRECISION=9")` e execute `python -m tests.preparar_malha_2025 caminho.geojsonl`.

Foram consultados o `LEIA-ME.txt` e a [Nota metodológica 01/2026, edição 2025](https://www.ibge.gov.br/biblioteca/visualizacao/livros/liv102268.pdf). O IBGE informa licença compatível com CC BY 4.0 para a MMD e derivados, com atribuição e as condições de uso descritas na nota. Fonte e edição constam dos mapas científicos. [Arquivo original oficial](https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2025/Brasil/).

### Classificação, navegação e exportação

- Por fonte, a associação usa EPSG:4326 e índice espacial sobre a malha detalhada. Só o interior de uma única UF recebe código. Pontos sobre uma borda externa, em múltiplas interseções, fora do território ou com coordenadas inválidas recebem situações distintas e continuam no balanço. O CSV espacial original preserva as coordenadas textuais e as referências. O CSV territorial filtrado acrescenta nomes, siglas e códigos e registra a base, o poluente de origem, a série, o ano, o setor e o combustível.
- Uma fonte para indicadores e ranking é a combinação de ID, coordenadas e altitude na série selecionada. Registros repetidos nessa chave são somados e contados separadamente. IDs distintos na mesma coordenada ficam consultáveis em um único marcador ou por páginas privadas. A potência é informada apenas quando a chave observada tem um valor coerente no inventário. O consumo é somado a partir das atividades da série.
- Mantido o mapa SVG local com JavaScript nativo. As interações incluem seleção de Brasil, região ou UF, clique no mapa e na comparação territorial, enquadramento animado, deslocamento, zoom, tela cheia, restauração e seleção de fontes pelo ranking Top 5/10/20. A seleção recarrega apenas consultas derivadas, sem recalcular o inventário. A participação territorial usa como denominador a massa classificada em UFs brasileiras; a visão geral informa também massas e fontes sem UF.
- As camadas opcionais mostram limites estaduais e regionais, fontes, massa total por UF, grade e massa por célula, e halos de intensidade visual. Halos não modelam dispersão, concentração, densidade ou exposição. A camada de grade está disponível para grades válidas de até 2.500 células; grades maiores continuam disponíveis no mapa científico. Viridis é a paleta padrão, e Cividis oferece uma alternativa com variação de luminosidade mais uniforme, ao lado de Plasma e Inferno.
- Prévia e download científicos são gerados separadamente pelo Matplotlib com malha detalhada, em português ou inglês, para Brasil, região ou UF. Conservam a série, território, unidade, paleta, escala, escopo de cores e estilo de marcadores. Os formatos são PNG a 300/600 DPI, PDF e SVG. As imagens têm cache privado por configuração com limite de 80 arquivos e 192 MiB. Os modos científicos distinguem pontos, células e massa total por UF. Quando a saída parte do mapa interativo, o estilo científico padrão é o mapa de fontes do território selecionado.

### Limites e próximos passos

As consultas usam SQLite privado por configuração espacial, com classificação reutilizável. O navegador recebe no máximo os 4.000 maiores pontos e as fontes adicionais do ranking; tabelas, balanços, CSV e indicadores cobrem toda a seleção. O agrupamento de coordenadas idênticas foi implementado. Canvas ou aglomeração por zoom pode ampliar o limite em uma etapa posterior, mantendo o acesso a cada fonte.

Leaflet foi avaliado como alternativa para ampliação futura. O SVG nativo já cobre o enquadramento animado, pan, zoom e interação com polígonos e marcadores sem adicionar dependência, mosaico ou servidor de mapas. A escolha de Canvas ou aglomeração depende de um perfil de uso com inventários maiores.

A exportação ZIP em lote permanece planejada. Para habilitá-la com segurança, faltam fila persistente de tarefas, orçamento de armazenamento por inventário, cancelamento e recuperação de interrupções da renderização. A interface entrega arquivos individuais sob demanda. A malha municipal fica como expansão futura. Continuam pendentes a confirmação do consumo real, a ampliação dos fatores Tier 1, a projeção anual autorizada e a segurança de produção. A Etapa 6 aguarda aprovação.

### Validação, desempenho e exemplos

- Os 18 testes automatizados passaram no Windows (Python 3.13.7) e no Docker (Python 3.11.18). A suíte inclui a malha detalhada e simplificada, casos de divisa, massa classificada e não classificada, agregação por fonte, filtros, potência e consumo, origens químicas distintas, escopos de cores, cache, privacidade e regressões das etapas anteriores.
- O fluxo Chrome passou com seleção do Rio de Janeiro pelo polígono, enquadramento automático, filtro de fontes, atualização de indicadores, troca de série, consulta individual, retorno ao Brasil, exportação regional e interface a 390 px.
- Em Windows, o primeiro carregamento do derivado detalhado levou 0,39 s. Com 1.000 fontes sintéticas, a primeira indexação levou 3,53 s (incluindo preparação inicial do GEOS); com 20.000 fontes e geometria já preparada, levou 2,76 s. As consultas filtradas a RJ após indexação demoraram 12 ms e 214 ms, respectivamente. Os picos de alocações Python rastreadas foram 31,62 MiB e 4,80 MiB. São ensaios locais sintéticos, sem medir toda a memória nativa ou carga concorrente.
- A geração dos cinco PNG sintéticos de avaliação levou 0,42–2,70 s por mapa na passagem medida. As respostas com cache levaram 8–22 ms.
- Em `exemplos/` estão os PNG de PM2.5 nacional, RJ, SP, por UF e por célula, além das capturas `interativo-brasil.png` e `interativo-rio.png`. Rode `python -m tests.exemplos_espaciais` para regenerar os mapas. Para capturar o fluxo Chrome, defina `PEGA_EXEMPLOS` com o caminho da pasta de exemplos e use o procedimento da Etapa 2.

Use o comando Uvicorn da Etapa 5 e abra **Resultados → Visão geral** para executar a distribuição espacial. Em **Imagens e gráficos → Mapas científicos**, escolha a visualização interativa e o território. A aba **Arquivos** reúne os links filtrados para mapas e CSV.

## Refinamento de UX/UI e consolidação da área de Resultados

**Status:** registro aprovado após os testes manuais da Etapa 5.1. A implementação fica programada para depois da conclusão da etapa científica. A Etapa 6 foi autorizada separadamente.

Os testes manuais aprovaram a aparência e o funcionamento do mapa interativo, incluindo seleção territorial, zoom e interação. O mapa SVG em JavaScript nativo, a malha IBGE 2025, os marcadores, filtros, indicadores, ranking e interações são a referência a preservar.

### Deslocamento vertical durante atualização do mapa

- **Sintoma relatado:** a página se desloca ligeiramente ao trocar poluente, território ou outra configuração.
- **Triagem no código:** `showMap()`, em `frontend/espacial.js`, oculta elementos auxiliares, limpa os indicadores e remove o mapa antes de aguardar a resposta. Depois reinserta o SVG ou a imagem. Essa sequência pode alterar a altura da página durante o carregamento e remover o elemento focado. As chamadas existentes a `scrollIntoView()` em `frontend/script.js` pertencem aos fluxos de importação, configuração e cálculo. A causa do deslocamento ainda precisa ser confirmada no navegador.
- **Critério de aceite:** reproduzir com dados sintéticos e medir a rolagem, o foco e a altura do contêiner antes, durante e depois da atualização. Preservar a posição da página e os filtros; manter o foco quando o controle continuar disponível. Atualizar somente o necessário e testar trocas sucessivas, com o mapa visível e com a página já rolada.

### Escopo programado

| Área | Requisitos |
| --- | --- |
| Visão geral | Manter o seletor de execução. Usar cards para fontes, atividades, poluentes, registros, ano, consumo com unidade, setor e combustível. Dar a cada etapa título, descrição, status, configurações e ação. Distinguir não iniciado, disponível, em processamento, concluído, erro e dependência pendente. Explicar bloqueios e oferecer consulta ou reexecução quando cabível. |
| Fluxo | Orientar importação e validação, cálculo, especiação, distribuição temporal, distribuição espacial, preparação para modelagem quando disponível e exportação. Manter opcionais as etapas derivadas e preservar o fluxo com poluentes originais. |
| Componentes | Padronizar botões, seletores, entradas, uploads, abas, cards, ícones, tipografia, espaçamentos, bordas, foco, mensagens e carregamento. Reutilizar CSS e preservar identidade visual, cores, mascote, vídeos e navegação. Melhorar contraste e legibilidade. |
| Central de exportações | Reunir inventário original, emissões, fatores, especiação, temporal, espacial, mapas e gráficos, modelagem quando disponível e metadados científicos. Mostrar somente arquivos disponíveis e identificar ícone, nome, descrição, formato, tamanho quando conhecido, execução e download. Avaliar ZIP de arquivos selecionados com manifesto e limites de recursos, mantendo autorização e expiração. |
| Tabelas | Onde aplicável, adicionar busca, ordenação, paginação, tamanho de página, cabeçalho fixo, unidades, notação científica e download correspondente. Conter a rolagem horizontal na tabela e identificar claramente prévias e conjuntos completos. |
| Gráficos e avisos | Organizar os gráficos científicos existentes por categoria e recolher configurações avançadas, preservando exportação de alta resolução. Dar aos avisos científicos uma seção própria, com alertas críticos visíveis e detalhes expansíveis. Preservar integralmente conservação de massa, resíduos, fatores indisponíveis e limitações metodológicas. |

### Verificação prevista

Executar a suíte existente e acrescentar testes de navegador para rolagem, persistência dos filtros, abas, estados e dependências das etapas, downloads e regressões. Conferir teclado, foco visível, identificação dos controles e layout a **390, 768, 1024, 1366 e 1920 px**. Produzir capturas antes e depois com dados sintéticos. A implementação deve preservar os resultados científicos, as equações, os fatores, os perfis temporais, a metodologia espacial, o isolamento das sessões e a expiração dos arquivos.

## Etapa 6 — Integração NetCDF, projeção temporal anual e preparação para WRF-Chem

A Etapa 5.1 e o registro de refinamento foram aprovados. A integração desta etapa acrescenta uma seção de preparação e links na área Resultados. O mapa interativo aprovado e a reformulação de UX/UI permanecem no seu escopo anterior.

### Grade do domínio e balanço de massa

- Leitura local de NetCDF clássico ou NetCDF-4 com uma grade Lambert estática (`MAP_PROJ=1`). Lê `XLAT` e `XLONG` na ordem `south_north, west_east`, com ou sem uma dimensão inicial `Time` de tamanho 1. Valida `GRID_ID`, `DX/DY`, paralelos padrão, meridiano central, coordenadas finitas e correspondência entre projeção declarada e centros.
- Reconstrói eixos pela mediana da origem inferida a partir de todos os centros, com o raio esférico de 6.370.000 m do WRF. A tolerância de validação é o menor entre 5 m e 1% do menor passo projetado. Pontos dentro da incerteza da borda, calculada a partir do desvio máximo verificado com piso numérico de 1 µm, são contabilizados separadamente. O balanço por série registra massa na grade, fora do domínio, em borda e com coordenada inválida.
- O `wrfinput_d01` local associado ao R declara `GRID_ID=2`, com 51 linhas por 63 colunas e `DX=DY=3.000 m`. O maior desvio por componente dos centros reconstruídos foi 2,695 m. O Python localizou os cinco centros de controle nas células esperadas. O nome do arquivo não foi usado para escolher o domínio e o arquivo de referência foi apenas lido.
- A execução local de `eixport::wrf_grid` retornou 3.213 polígonos, porém usa um raster regular em longitude/latitude com os extremos dos centros como envelope e numeração de raster. No teste dos quatro centros de canto e do centro do domínio, o R retornou respectivamente sem interseção, 3.213, sem interseção, sem interseção e 1.607. A reconstrução Lambert do Python retornou 1, 63, 3.151, 3.213 e 1.607 em índice linear de base 1, com coluna variando mais rápido. O NetCDF intermediário usa os centros e o espaçamento projetado declarados pelo WRF. A equivalência numérica com a grade legada do R não foi estabelecida. Confirme a convenção Lambert para a futura escrita de `wrfchemi`.
- Massas em gramas são acumuladas por célula, preservando a base original ou especiada, o par poluente de origem/série e os fatores e referências no JSON. O balanço da especiação acompanha a base derivada. Saldos residuais seguem fora da massa distribuída.

### Projeção anual e artefatos

A projeção é opcional e exige que a pessoa selecione UTC ou informe um deslocamento fixo (por exemplo, `-03:00`). O mesmo relógio é aplicado a toda a execução. O calendário gregoriano proléptico tem 8.760 horas ou 8.784 com 29 de fevereiro. Cada peso bruto é o produto semanal × horário definido pelo R, e sua fração é obtida dividindo esse peso pela soma dos pesos sobre todas as horas do ano. A projeção conserva a massa da base no domínio ao longo de todo o ano e pressupõe que a base represente o ano do inventário. A coordenada temporal guarda o centro de cada intervalo e limites de uma hora, referidos a UTC. Não foi aplicada troca de fuso por fonte, horário de verão ou um calendário de simulação específico.

`emissoes-grade.nc` guarda `inventory_mass(series, south_north, west_east)` em g, eixos em metros, limites de células, coordenadas geográficas, metadados Lambert e o balanço numérico por série. Quando solicitado, inclui `hour_fraction(time)` e, em até 12 milhões de valores, `hourly_mass(time, active)` com os índices de série, linha e coluna de cada par ativo. Para produtos maiores, reconstrua a massa horária multiplicando a massa por célula pela fração. Essa fatoração reduz o volume sem alterar a equação. Massas por intervalo não são taxas nem concentrações. Os metadados de coordenadas e intervalos seguem as descrições CF pertinentes; uma certificação geral ainda não foi realizada.

A geração requer sessão autorizada, usa arquivos temporários, reutiliza configurações iguais e publica NetCDF e JSON sob a execução escolhida. Os limites são 256 MiB por envio de domínio, 500.000 células, 36 milhões de valores série × grade e oito configurações por base e cálculo. O domínio enviado é descartado ao final. A preparação fica em **Resultados → Visão geral → Preparação para modelagem · NetCDF**, o balanço em **Tabelas** e os downloads em **Arquivos**.

### Decisões pendentes para um produto wrfchemi

O R chama `eixport::wrf_create` com domínio fixo 1, `io_style_emissions=1`, dois deslocamentos de 12 horas, `n_aero=15` e nomes `E_*`. Lê `Times` em UTC e escreve uma matriz com um nível, usando a ordem coluna, linha, nível, tempo. Sua conversão supõe área fixa de 3 × 3 km e calcula `ug/m2/s` ou `mol/km2/hr` a partir de classificação por espécie e massa molecular. O NetCDF PEGA desta etapa é intermediário e mantém massas e dimensões explícitas.

Para avançar a escrita de `wrfchemi`, confirmar o `GRID_ID` (inclusive esclarecer o d01 de nome versus domínio 2 nos metadados deste arquivo), a versão e configuração do WRF-Chem, o mecanismo químico e `chem_opt/emiss_opt`, mapeamento e eventual combinação das origens de cada espécie, massas moleculares e unidades (inclusive PSI e PSO4), área física das células, relógio e intervalo de simulação e distribuição vertical. A investigação da Etapa 6.1 esclarece os significados de `n_aero` e `kemit`. Solicitar um arquivo-alvo ou configuração verificável e uma validação por leitura e execução do modelo antes de declarar compatibilidade.

Referências técnicas: [WRF — projeções e grade](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html), [WRF — raio de referência no código](https://github.com/wrf-model/WRF/blob/master/share/module_llxy.F) e [CF — coordenadas, limites e métodos de célula](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.pdf). Permanecem pendentes a confirmação do consumo real, a ampliação Tier 1, a segurança da implantação e o refinamento de UX/UI.

### Validação e execução

- Os 21 testes passaram no Windows com Python 3.13.7 (21,604 s) e no Docker com Python 3.11.18 (14,942 s). O teste de ponta a ponta no Chrome também passou, com inventário e domínio sintéticos em armazenamento temporário.
- No teste sintético em grade assimétrica 3 × 2, o PM2.5 totalizou 438.900 g na base. A grade recebeu 399.000 g nas duas células esperadas. O balanço registrou 26.600 g fora do domínio e 13.300 g em borda. A soma das 8.760 alocações de cada célula recuperou a massa mapeada.
- Em teste independente de interoperabilidade, o R/`ncdf4` releu um NetCDF sintético de 3 × 2 com 8.784 horas em relógio fixo e confirmou 90.000 g antes e depois da alocação. Os testes automatizados cobrem também leitura do formato clássico, rejeição de projeção e geometrias incompatíveis, calibração temporal, formato fatorado, base especiada, metadados, privacidade, cache e exclusão.
- O cenário Chrome testa a geração anual com arquivo sintético, download do NetCDF e o fluxo completo aprovado anteriormente, incluindo o mapa interativo. A validação não incluiu execução do WRF-Chem.

Na raiz do projeto, instale `requirements-dev.txt` no ambiente virtual e inicie com `./.venv/Scripts/python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8001`. Para repetir a suíte, rode `./.venv/Scripts/python.exe -m unittest discover -s tests -v`. O teste Chrome segue o procedimento da Etapa 2.

## Etapa 6.1 — Auditoria científica e preparação da exportação wrfchemi

A Etapa 6 foi aprovada no escopo de leitura de domínio, agregação, calendário opcional e NetCDF intermediário. A auditoria é independente, local e somente de leitura. Não houve alteração no código R, nas rotas de produção, nos arquivos WRF originais, no NetCDF intermediário ou no mapa interativo.

### Domínio e procedência

| Evidência | Valor observado |
| --- | --- |
| Nome de entrada | `wrfinput_d01` |
| Domínio do cabeçalho | `GRID_ID=2`, `PARENT_ID=1`, `PARENT_GRID_RATIO=3`, `I_PARENT_START=48`, `J_PARENT_START=40` |
| Grade de massa | 63 colunas × 51 linhas no arquivo. Os atributos dimensionais escalonados informam 64 × 52. `DX=DY=3.000 m` projetados. |
| Projeção | Lambert, `MAP_PROJ=1`, `TRUELAT1=-23`, `TRUELAT2=-24`, `STAND_LON=-45`, `MOAD_CEN_LAT≈-23,55°` |
| Identidade dos arquivos | O `wrfinput` traz o título de pré-processamento `REAL_EM V3.9.1.1`. Os dez exemplos `wrfchemi`, oito nomeados `d01` e dois `d02`, usam o título `Anthropogenic emissions for WRF V4.0`, padrão do gerador eixport. Nenhum título determina a versão do executável usado numa simulação. |
| Concordância dos exemplos | Os dez exemplos repetem o aninhamento, projeção e dimensões. `XLAT/XLONG` coincidem numericamente com a entrada. O cabeçalho é coerente com a grade de um domínio aninhado 2. |

A busca no projeto Python, no projeto R e no pacote PEGA local não encontrou um `namelist.input`, um `wrfout`, um `wrf.exe` ou um log de execução que determine o caso de simulação. A evidência identifica a geometria arquivada como domínio 2. O domínio a ser carregado pela próxima simulação ainda depende de confirmação. [Manual eixport](https://atmoschem.github.io/eixport/reference/wrf_create.html)

### Geometria e orientação

- **Lambert, arquivo local:** os 3.213 centros `XLAT/XLONG` retornaram ao índice esperado. A coluna cresce com X, a linha cresce com Y e a coluna varia mais rápido no índice linear. Diferença entre centros projetados e reconstruídos: média 1,130 m, RMSE 1,236 m, P95 1,943 m e máximo 2,766 m. O maior desvio por eixo da Etapa 6 permanece 2,695 m. A ida e volta numérica de coordenadas teve erro geodésico máximo de aproximadamente 6,7 × 10⁻⁹ m. Esse último número confirma estabilidade numérica, sem implicar essa precisão nas coordenadas de entrada.
- **R/eixport real:** `sf::st_intersects` sobre os mesmos centros encontrou 3.210 interseções únicas, três centros sem célula e nenhuma múltipla. O índice coincide diretamente em 63 centros e em 3.210 quando se inverte a orientação de Y. A emulação do raster regular em graus, que usa a extensão dos centros e não usa a geometria S2, difere da interseção real em três pontos de extremo. Nessa emulação, a distância entre o centro WRF e o centro da célula legada atribuída foi em média 981 m, com RMSE 1.049 m e máximo 1.816 m.
- **Vértices, bordas e exterior:** 12 casos passaram no Lambert real e em cada uma de três grades sintéticas com `DX/DY` de 1.000/1.500, 3.000/4.000 e 18.000/20.000 m. No R, os quatro vértices e os dois pontos interiores junto a cantos da grade Lambert ficaram sem interseção. Nos dois limites compartilhados Lambert, o R atribuiu uma célula. Ambos encontraram uma célula nos dois lados testados de um limite interior e excluíram os dois pontos externos. A faixa de borda Lambert mantém as massas ambíguas separadas das células.

A recomendação é manter a reconstrução Lambert para a futura exportação, usar os índices de massa do arquivo alvo explicitamente e preservar o tratamento auditável de borda. A grade raster do R permanece referência de comparação. [WRF — projeções e grade de massa](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html)

### Área física de célula

Para Lambert, a convenção de escala de mapa fornece uma aproximação no centro em m²: `DX × DY / (MAPFAC_MX × MAPFAC_MY)`. Com fator isotrópico, equivale a `DX × DY / MAPFAC_M²`. Os fatores da grade de massa são adimensionais. A entrada local traz `XLAT/XLONG` e os parâmetros de projeção, mas omite os três campos MAPFAC.

A auditoria integra na esfera WRF a área projetada dividida pelo fator areal do Jacobiano, pela quadratura Gauss–Legendre 3 × 3. O cálculo independente desfaz a projeção na borda da célula, segmenta os quatro lados e soma a área do polígono geodésico na mesma esfera. Em 121 células, a maior diferença entre a integral e a geodésia com 32 segmentos por lado foi **4,32 × 10⁻⁹%**. A mudança de 8 para 32 segmentos foi de no máximo **2,72 × 10⁻⁸%**. As áreas integradas ficaram entre **8.998.533 e 9.000.685 m²**, com média **9.000.138 m²**, frente a 9.000.000 m² nominais. Esses desvios quantificam a diferença neste domínio, sem validar a área fixa em outros domínios.

Recomenda-se a integral de área física da célula, confrontada com MAPFAC quando disponível e com a convenção do caso WRF-Chem. Para um futuro fluxo, `µg m⁻² s⁻¹ = massa_g × 10⁶ / (área_m² × intervalo_s)`. Para fluxo molar, `mol km⁻² h⁻¹ = massa_g / (MW_g_mol × área_km² × intervalo_h)`. A aplicação exige que unidade, MW, relógio e espécie já tenham sido aprovados. Essas conversões não foram aplicadas ao NetCDF intermediário. [Registro MAPFAC do WRF](https://github.com/wrf-model/WRF/blob/master/Registry/Registry.EM_COMMON.var) · [Exemplo de área de célula no código WRF](https://github.com/wrf-model/WRF/blob/master/var/da/da_main/da_solve.inc)

### Química e estrutura de arquivo

- Cada exemplo local contém 63 variáveis `E_*`, 12 registros separados por 3.600 s em data de referência de agosto de 2011 e um nível em `emissions_zdim_stag`. Na ordem NetCDF/Python, as variáveis são `(Time, emissions_zdim_stag, south_north, west_east)`. O núcleo R solicita o estilo 1 de dois blocos de 12 horas, e o campo `Times` dos exemplos não codifica fuso. Esses arquivos não estabelecem o período do inventário nem o calendário aceito pela futura simulação.
- A documentação de **eixport 0.6.2** esclarece que `n_aero=15` classifica espécies pelo fim da lista entregue ao gerador. `kemit` define os níveis e tem padrão 1. Portanto, um nível no arquivo observado é coerente com o padrão do gerador. A ordem de entrada e o mecanismo da simulação ainda devem ser confirmados. [Manual eixport](https://atmoschem.github.io/eixport/reference/wrf_create.html)
- Os arquivos declaram 48 variáveis em `mol km^-2 hr^-1` e 15 em `ug m^-2 s^-1`. Entre 45 linhas do perfil PEGA (44 nomes de destino únicos), todas têm coincidência nominal, mas **21 linhas divergem das unidades do ramo de conversão do R**. Nenhum mecanismo, `chem_opt`, `emiss_opt` ou `emiss_inpt_opt` ficou estabelecido.

| Origem no PEGA | Linhas com nome presente | Unidade literal coincide com a conversão R | Exemplos críticos |
| --- | ---: | ---: | --- |
| PM2.5 | 16 | 3 | PAL e PNO3 recebem unidade molar no cabeçalho e tratamento particulado no R. PSI tem unidade de massa no cabeçalho, cai no ramo molar no R e o perfil PEGA carece de MW para PSI. |
| SOx | 2 | 1 | SO2 tem unidade de massa no cabeçalho e unidade molar no R. PSO4 converge em unidade, mas também existe na série originada de PM2.5. |
| NOx | 2 | 2 | NO2 e HONO coincidem nominalmente e em unidade. O consumo pelo mecanismo continua pendente de confirmação. |
| NMVOC | 25 | 18 | SOAALK, TOL, UNK, XYLMN, TERP, XYL e SULF têm unidade de massa no cabeçalho e unidade molar no R. |

A tabela completa está em [correspondência nominal](docs/wrfchemi-correspondencia-nominal.csv). Ela mantém as duas origens de PSO4, as massas moleculares ausentes e os pares explicitamente pendentes de validação. As outras 19 variáveis do exemplo, incluindo espécies fora do perfil químico, também precisam de correspondência documentada. A coincidência de nomes e unidades não estabelece um mapeamento químico aceito. [Registro químico do WRF](https://github.com/wrf-model/WRF/blob/master/Registry/registry.var_chem)

### Relógios da atividade, da fonte e do modelo

O NetCDF intermediário mantém UTC e deslocamento fixo explícito como **relógio do perfil**, comum a toda a execução. O horário civil de cada fonte é uma escolha espacial e histórica distinta. Os instantes UTC e os limites do intervalo são o referencial de armazenamento. O período e a convenção da simulação devem vir do caso WRF-Chem. A diferença entre os instantes do intervalo determina a duração usada na conversão de unidades.

Na auditoria IANA de `America/Sao_Paulo`, 2018 apresentou 8.760 horas decorridas, com um rótulo civil ausente e um repetido. 2019 apresentou **8.761 horas decorridas** no ano civil, com um rótulo repetido. 2020 apresentou 8.784 horas, sem troca de deslocamento. Uma futura projeção com IANA deve registrar a versão da base de fusos, associar fonte a fuso por regra aprovada, enumerar os instantes em UTC e definir como alocar o peso de uma hora ausente ou repetida. Quando o deslocamento fracionário corta intervalos do perfil, a subdivisão requer metodologia explícita. Depois, a normalização deve ser feita por fonte e período aprovado. A auditoria IANA não altera a projeção atual. [Python zoneinfo](https://docs.python.org/3/library/zoneinfo.html)

### Requisitos para habilitar a exportação

Para escrever e validar `wrfchemi`, fornecer:

1. O `namelist.input` da simulação pretendida e a versão ou revisão do WRF-Chem. Incluir `&domains`, `&time_control` e `&chem`, em particular domínio, aninhamento, período, `chem_opt`, `emiss_opt`, `emiss_inpt_opt`, esquema de aerossol, `kemit`, `io_style_emissions`, `auxinput5_interval_m` e `frames_per_auxinput5` aplicáveis.
2. Um `wrfinput`/ `geo_em` do domínio aceito com fatores de mapa, se disponíveis, e um `wrfchemi` já lido pelo mesmo executável ou o registro de emissores do mecanismo acompanhado de log de leitura. Confirmar domínio 2 e a adoção da reconstrução Lambert para esse caso.
3. A tabela aprovada de séries PEGA → variáveis alvo, unidades, MW quando exigido, combinação de origens, tratamento de séries sem destino e a regra vertical ou parâmetros de lançamento necessários. Confirmar área física, relógio do perfil, período da simulação e regras temporais pertinentes.

Depois dessas confirmações, verificar leitura e execução pelo WRF-Chem e reconstruir as massas das taxas gravadas usando área, camada e duração. Separar a massa fora de domínio, as exclusões aprovadas e os saldos. Os exemplos locais fornecem evidência de estrutura, mas as divergências de unidade e a configuração ausente impedem uma exportação experimental defensável nesta etapa.

Para repetir a auditoria sem modificar as entradas:

```powershell
./.venv/Scripts/python.exe -m backend.services.auditoria_wrf D:/APP_PEGA/wrf/wrfinput_d01 --alvo D:/APP_PEGA/wrf/wrfchemi_00z_d02 --relogio 2019 America/Sao_Paulo
```

**Validação:** 25 testes passaram no Windows (21,909 s) e no Docker com Python 3.11.18 (16,250 s). Os quatro testes novos cobrem geometria em três resoluções, cálculo independente de área e MAPFAC sintético, estrutura e unidades de um alvo sintético, e transições IANA. A regressão de ponta a ponta passou no Chrome, incluindo NetCDF intermediário e mapa interativo. A suíte Docker usou a imagem local de auditoria e o armazenamento de pesquisa ficou fora dos testes.

O refinamento de UX/UI permanece registrado para depois da etapa científica. A Etapa 7 aguarda aprovação.
