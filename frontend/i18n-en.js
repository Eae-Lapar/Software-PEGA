const englishUI = `
PEGA | Inventários de Emissões|PEGA | Emission Inventories
Pular para o conteúdo|Skip to content
PEGA, início|PEGA, home
Navegação principal|Main navigation
Idioma da interface|Interface language
Menu|Menu
Início|Home
Sobre|About
Inventário|Inventory
Resultados|Results
Conectando...|Connecting...
Servidor online|Server online
Servidor indisponível|Server unavailable
TECNOLOGIA E CIÊNCIA ATMOSFÉRICA|ATMOSPHERIC SCIENCE AND TECHNOLOGY
Inventários de|Atmospheric
emissões atmosféricas.|emission inventories.
Uma plataforma para automatizar, padronizar e integrar o processamento de inventários de emissões atmosféricas.|A platform to automate, standardize, and integrate atmospheric emission inventory processing.
Iniciar inventário|Start inventory
Conhecer o PEGA|About PEGA
Seu navegador não suporta vídeos.|Your browser does not support video.
Sobre o PEGA|About PEGA
Inventariar|Build an inventory
Valide as fontes, configure os fatores e calcule as emissões.|Validate sources, configure factors, and calculate emissions.
Analisar|Analyze
Explore espécies, perfis temporais, territórios e grades.|Explore species, temporal profiles, territories, and grids.
Exportar|Export
Consulte tabelas, gráficos, relatórios e produtos para modelagem.|Access tables, figures, reports, and modeling products.
Importação|Import
Disponível|Available
Validação|Validation
Pendente|Pending
Configuração|Configuration
Cálculo das emissões|Emission calculation
Análises complementares|Additional analyses
Opcionais|Optional
Resultados e exportações|Results and exports
Etapas do inventário|Inventory steps
DADOS DE ENTRADA|INPUT DATA
Importação de dados|Data import
Envie a planilha contendo os dados das fontes de emissão.|Upload the spreadsheet containing emission source data.
Arraste e solte sua planilha|Drag and drop your spreadsheet
CSV, TXT ou XLSX · até 50 MB|CSV, TXT, or XLSX · up to 50 MB
Selecionar arquivo|Select file
Colunas obrigatórias|Required columns
Identificador da fonte ou atividade.|Source or activity identifier.
Tipo de combustível.|Fuel type.
Potência em MW.|Power in MW.
Latitude em graus decimais.|Latitude in decimal degrees.
Longitude em graus decimais.|Longitude in decimal degrees.
Ano de referência.|Reference year.
Consumo de combustível em GJ.|Fuel consumption in GJ.
Cada linha representa uma atividade. Confira as unidades antes do envio.|Each row represents one activity. Check the units before uploading.
Enviando arquivo...|Uploading file...
Validando dados da planilha...|Validating spreadsheet data...
Registros importados|Imported records
Anos identificados|Years found
Combustíveis|Fuels
Prévia dos dados|Data preview
Exibição de até 20 registros.|Showing up to 20 records.
Importar outro arquivo|Import another file
Avançar para processamento|Continue to processing
Excluir inventário|Delete inventory
Configuração e cálculo|Configuration and calculation
Selecione o recorte e revise os fatores antes de calcular as emissões.|Select the scope and review the factors before calculating emissions.
Setor|Sector
Ano|Year
Combustível|Fuel
Fatores aplicados automaticamente|Automatically applied factors
Calcular emissões|Calculate emissions
Os resultados ficam disponíveis após o cálculo de emissões.|Results are available after calculating emissions.
Execuções do inventário|Inventory runs
Visão geral|Overview
Tabelas|Tables
Imagens e gráficos|Figures and charts
Arquivos|Files
Indicadores da execução|Run indicators
Ano do inventário|Inventory year
Fontes|Sources
Atividades|Activities
Poluentes|Pollutants
Registros calculados|Calculated records
Consumo energético|Energy consumption
Execute as análises opcionais conforme o objetivo do inventário.|Run optional analyses as needed for your inventory.
Especiação química|Chemical speciation
Distribua a massa por espécie e confira o saldo por poluente de origem.|Allocate mass by species and check the balance by parent pollutant.
Executar especiação química|Run chemical speciation
Ver resultados|View results
Distribuição temporal|Temporal distribution
Aplique os perfis relativos de 24, 7 e 168 intervalos, sem calendário.|Apply the relative profiles of 24, 7, and 168 intervals without a calendar.
Base temporal|Temporal basis
Poluentes originais|Original pollutants
Executar distribuição temporal|Run temporal distribution
Distribuição espacial|Spatial distribution
Explore fontes e territórios do IBGE ou agregue as massas em uma grade.|Explore sources and IBGE territories or aggregate masses on a grid.
Base espacial|Spatial basis
Grade opcional (GeoJSON)|Optional grid (GeoJSON)
EPSG da grade|Grid EPSG
Executar distribuição espacial|Run spatial distribution
Para agregar em grade, forneça os polígonos das células com a propriedade id_grid e o EPSG das coordenadas.|To aggregate on a grid, provide cell polygons with the id_grid property and the coordinate EPSG code.
Modelagem atmosférica|Atmospheric modeling
Agregue massas na grade Lambert de um|Aggregate masses on the Lambert grid of a
. O NetCDF intermediário armazena massas em gramas, sem conversão para|. The intermediate NetCDF stores masses in grams without conversion to
Preparação para modelagem · NetCDF|Modeling preparation · NetCDF
Base|Basis
Domínio NetCDF|NetCDF domain
Estimar no calendário anual|Estimate on the annual calendar
Relógio do perfil|Profile time reference
UTC ou -03:00|UTC or -03:00
Preparar NetCDF|Prepare NetCDF
UTC ou deslocamento fixo para todas as fontes. Os pesos do perfil são normalizados sobre o calendário do ano do inventário. Não há ajuste de horário de verão.|Use UTC or a fixed offset for all sources. Profile weights are normalized over the inventory year. Daylight saving time is not applied.
Ver domínio WRF|View WRF domain
Emissões por poluente|Emissions by pollutant
Prévia das emissões por atividade e fonte|Emission preview by activity and source
Fatores e referências usados|Applied factors and references
Balanço de massa por poluente de origem|Mass balance by parent pollutant
Emissões por espécie e poluentes preservados|Emissions by species and retained pollutants
Perfil, frações e massas moleculares do R|R profile, fractions, and molecular weights
Prévia dos resultados por atividade|Results preview by activity
Distribuição temporal relativa|Relative temporal distribution
Massas da base por poluente ou espécie|Base masses by pollutant or species
Perfil horário|Hourly profile
Perfil semanal|Weekly profile
Perfil combinado|Combined profile
Série da tabela|Table series
Prévia das fontes (até 100 registros)|Source preview (up to 100 records)
Prévia por célula (até 100 registros)|Cell preview (up to 100 records)
Balanço de massa · domínio NetCDF|Mass balance · NetCDF domain
Categoria|Category
Emissões|Emissions
Especiação|Speciation
Temporal|Temporal
Espacial|Spatial
Visualização|Visualization
Poluente ou espécie|Pollutant or species
Unidade|Unit
Território|Territory
Data inicial|Start date
Data final|End date
Configurações avançadas|Advanced settings
Escala|Scale
Logarítmica|Logarithmic
Paleta|Palette
Ordenação|Sort order
Maior massa primeiro|Highest mass first
Menor massa primeiro|Lowest mass first
Número de fontes|Number of sources
Início da comparação|Comparison start
Fim da comparação|Comparison end
Idioma da figura|Figure language
Português|Portuguese
Gráfico temporal|Temporal chart
Perfil de 168 horas|168-hour profile
Mapa de calor temporal|Temporal heatmap
Peso relativo (%)|Relative weight (%)
Gramas (g)|Grams (g)
Quilogramas (kg)|Kilograms (kg)
Toneladas (t)|Tonnes (t)
Mapa interativo|Interactive map
Mapa científico|Scientific map
Tipo de mapa científico|Scientific map type
Distribuição por fonte|Distribution by source
Massa agregada por UF|Aggregated mass by state
Massa total por região|Total mass by region
Idioma|Language
Marcadores|Markers
Cor|Color
Tamanho|Size
Cor e tamanho|Color and size
Nível territorial|Territorial level
Brasil|Brazil
Região|Region
Unidade federativa|State
Escala de cores|Color scale
Nacional|National
Território selecionado|Selected territory
Voltar ao Brasil|Return to Brazil
Restaurar enquadramento|Reset view
Tela cheia|Full screen
Camadas|Layers
Limites estaduais|State boundaries
Limites regionais|Regional boundaries
Fontes pontuais|Point sources
Massa total por UF|Total mass by state
Intensidade visual das emissões|Visual emission intensity
Grade e massa por célula|Grid and mass per cell
Ranking de fontes|Source ranking
Exibir|Show
Decrescente|Descending
Crescente|Ascending
Comparação territorial|Territorial comparison
Comparar|Compare
UFs|States
Regiões|Regions
Selecionar todos|Select all
Baixar selecionados em ZIP|Download selected as ZIP
Baixar execução em ZIP|Download run as ZIP
Exportações com os filtros de Imagens e gráficos|Exports with current figure filters
Personalizar relatório|Customize report
Documento|Document
Relatório|Report
Completo|Full
Resumo executivo|Executive summary
Conteúdo|Content
Seções adicionais|Additional sections
Figuras e território|Figures and territory
Incluir gráfico de emissões|Include emission chart
Incluir mapa científico|Include scientific map
Território do mapa|Map territory
Gerar PDF personalizado|Generate customized PDF
PEGA — Inventários de Emissões Atmosféricas|PEGA — Atmospheric Emission Inventories
Visualização ampliada|Enlarged visualization
Fechar visualização|Close visualization
Figura científica ampliada|Enlarged scientific figure
Mapa científico ampliado|Enlarged scientific map
Ampliar imagem|Enlarge image
↓ Baixar imagem|↓ Download image
Formato|Format
Formato da figura|Figure format
Resolução|Resolution
Resolução PNG|PNG resolution
Baixar|Download
Baixar CSV|Download CSV
Inventário e emissões|Inventory and emissions
Mapas e gráficos|Maps and figures
Relatórios científicos|Scientific reports
Fatores e referências|Factors and references
Gerado sob demanda|Generated on demand
Buscar na tabela|Search table
Anterior|Previous
Próxima|Next
Ordenar coluna|Sort column
Nenhum registro|No records
Concluída|Completed
Em processamento|Processing
Opcional|Optional
Requer atenção|Needs attention
Selecione|Select
Indisponível|Unavailable
Fonte|Source
Poluente|Pollutant
Emissão|Emission
Emissão (g)|Emission (g)
Atividade (GJ)|Activity (GJ)
Poluente de origem|Parent pollutant
Espécie|Species
Espécie ou poluente|Species or pollutant
Fração|Fraction
Saldo (g)|Residual (g)
Derivado (g)|Allocated (g)
Soma das frações|Sum of fractions
Massa molecular (g/mol)|Molecular weight (g/mol)
Fator|Factor
Referência|Reference
Observação|Note
Totais por poluente|Totals by pollutant
Ranking por fonte|Source ranking
Participação das fontes|Source shares
Emissão acumulada das fontes|Cumulative source emissions
Distribuição entre fontes|Distribution across sources
Emissões por UF|Emissions by state
Emissões por região|Emissions by region
Balanço de massa|Mass balance
Massa por espécie|Mass by species
Frações do perfil|Profile fractions
Mapa de calor relativo|Relative heatmap
Massas mensais|Monthly masses
Massas diárias|Daily masses
Acumulados por hora do dia|Totals by hour of day
Série anual|Annual series
Calendário de massas diárias|Daily mass calendar
Massa por célula WRF|Mass per WRF cell
Domínio computacional WRF|WRF computational domain
Perfis relativos interativos|Interactive relative profiles
Especiada|Speciated
Emissões agregadas em grade|Grid-aggregated emissions
Form as linhas|Rows
Formato inválido. Envie CSV, TXT ou XLSX.|Invalid format. Upload CSV, TXT, or XLSX.
O arquivo excede o limite de 50 MB.|The file exceeds the 50 MB limit.
Inventário ou cálculo indisponível.|Inventory or calculation unavailable.
Resultado indisponível.|Result unavailable.
Inventário excluído com sucesso.|Inventory deleted successfully.
Excluir este inventário e todas as suas execuções?|Delete this inventory and all its runs?
Cálculo concluído.|Calculation complete.
Carregando resultado…|Loading result…
Carregando inventário…|Loading inventory…
Inventário restaurado.|Inventory restored.
Calculando emissões…|Calculating emissions…
Preparando ZIP…|Preparing ZIP…
Gerando relatório…|Generating report…
Gerando visualização científica…|Generating scientific visualization…
Atualizando mapa…|Updating map…
Atualizando a visualização. A imagem anterior permanece visível durante a geração.|Updating the visualization. The previous image remains visible while it is generated.
Consultando setores suportados…|Loading supported sectors…
Selecione o setor|Select a sector
Selecione o ano|Select a year
Selecione o combustível|Select a fuel
Selecione uma execução|Select a run
Processando fontes…|Processing sources…
Executando especiação química…|Running chemical speciation…
Calculando distribuição relativa…|Calculating relative distribution…
Consultando resultados temporais…|Loading temporal results…
Validando domínio e gerando NetCDF…|Validating domain and generating NetCDF…
Fontes pontuais processadas.|Point sources processed.
Perfil relativo disponível.|Relative profile available.
Selecione um território ou fonte. Arraste para deslocar e use a rolagem ou os botões para zoom.|Select a territory or source. Drag to pan and use scrolling or the buttons to zoom.
Cartografia: IBGE, Malha UF 2025 (adaptada).|Basemap: IBGE, 2025 State Boundaries (adapted).
Aproximar mapa|Zoom in
Afastar mapa|Zoom out
Pré-visualização científica|Scientific preview
Mapa científico da série selecionada|Scientific map of the selected series
Progresso do ZIP|ZIP progress
Dados padronizados|Standardized data
Emissões calculadas|Calculated emissions
Metadados da execução|Run metadata
Emissões especiadas|Speciated emissions
Resumo por espécie|Summary by species
Perfil químico|Chemical profile
Balanço da especiação|Speciation balance
Resumo|Summary
Fatores utilizados|Applied factors
Metadados|Metadata
Relatório científico|Scientific report
Gráfico nacional da base original em gramas.|National chart for the original basis in grams.
Fontes no IBGE 2025 em gramas.|Sources on the IBGE 2025 basemap in grams.
Exportação do mapa científico por fonte com o poluente e o território selecionados.|Export of the scientific source map for the selected pollutant and territory.
`.trim().split("\n").map(line => line.split("|"));

const englishPatterns = [
    ["{} de {} selecionados", "{1} of {2} selected"],
    ["{} selecionados", "{1} selected"],
    ["Execução {} · {} · {}", "Run {1} · {2} · {3}"],
    ["{} por página", "{1} per page"],
    ["Buscar em {}", "Search {1}"],
    ["Registros por página de {}", "Records per page for {1}"],
    ["{}–{} de {}", "{1}–{2} of {3}"],
    ["{}–{} de {} ({} na tabela)", "{1}–{2} of {3} ({4} in table)"],
    ["Selecionar {} · {}", "Select {1} · {2}"],
    ["Selecionar {}", "Select {1}"],
    ["Baixar mapa ({})", "Download map ({1})"],
    ["Baixar gráfico filtrado ({})", "Download filtered chart ({1})"],
    ["Baixar fontes do território (CSV)", "Download territory sources (CSV)"],
    ["Baixar {} ({})", "Download {1} ({2})"],
    ["Especiação concluída. {} registros derivados.", "Speciation complete. {1} derived records."],
    ["Grade processada · EPSG:{}.", "Grid processed · EPSG:{1}."],
    ["Massa acumulada por intervalo · {}", "Accumulated mass per interval · {1}"],
    ["{} de {} arquivos. {}", "{1} of {2} files. {3}"],
    ["ZIP pronto com {} arquivos. Consulte o manifesto para ver a lista.", "ZIP ready with {1} files. See the manifest for details."],
    ["ZIP pronto com {} arquivos. Consulte o manifesto para ver a lista. Omitidos: {}", "ZIP ready with {1} files. See the manifest for details. Omitted: {2}"],
    ["O ZIP excedeu 256 MiB descompactados ao incluir {}. Selecione menos arquivos.", "The ZIP exceeded 256 MiB uncompressed while adding {1}. Select fewer files."],
    ["O ZIP atingiu 120 segundos de processamento ao incluir {}. Selecione menos arquivos.", "ZIP processing reached 120 seconds while adding {1}. Select fewer files."],
    ["Mapa nacional · {} · {}", "National map · {1} · {2}"],
    ["Perfil relativo disponível. Os saldos da especiação permanecem fora da alocação.", "Relative profile available. Speciation residuals are excluded from the allocation."],
    ["Capa, identificação, metodologia, totais e alertas{}.", "Cover, identification, methodology, totals, and alerts{1}."],
];
englishUI.push(...`
Base nacional|National basis
logarítmica; zero em cinza|logarithmic; zero shown in gray
linear|linear
sem faixa de cores|no color range
Sem massa classificada por UF.|No mass assigned to a state.
A grade excede o limite de 2.500 células da camada interativa.|The grid exceeds the 2,500-cell interactive layer limit.
Halos indicam intensidade visual das emissões pontuais. Sem interpretação como concentração, dispersão ou exposição.|Halos visualize point emission intensity. They do not represent concentration, dispersion, or exposure.
Nenhuma fonte para esta seleção.|No sources for this selection.
Coordenadas inválidas|Invalid coordinates
UF não classificada|State not assigned
Página anterior|Previous page
Próxima página|Next page
Tela cheia indisponível neste navegador.|Full-screen mode is unavailable in this browser.
Mapa indisponível para esta seleção.|Map unavailable for this selection.
Consultando fatores científicos…|Loading scientific factors…
Consultando combustíveis do setor…|Loading fuels for the sector…
Selecione as referências obrigatórias.|Select the required references.
Nenhum fator válido disponível.|No valid factors available.
Histórico indisponível. Recarregue a página para tentar novamente.|Run history unavailable. Reload the page to try again.
Excluindo inventário…|Deleting inventory…
Envio cancelado.|Upload canceled.
Não foi possível ler a planilha XLSX.|Could not read the XLSX spreadsheet.
Arquivo excede o limite de 50 MB.|The file exceeds the 50 MB limit.
Não foi possível gerar a imagem.|Could not generate the image.
Relatório indisponível.|Report unavailable.
Relatório pronto. Download solicitado.|Report ready. Download requested.
Base indisponível. Para usar espécies, execute primeiro a especiação química.|Basis unavailable. Run chemical speciation before using species.
Base indisponível. Execute a especiação para usar espécies.|Basis unavailable. Run speciation before using species.
Resposta inesperada do servidor.|Unexpected response from the server.
Origem|Origin
Série|Series
Base (g)|Basis (g)
Na grade (g)|On grid (g)
Fora do domínio (g)|Outside domain (g)
Em borda (g)|On boundary (g)
Coordenada inválida (g)|Invalid coordinate (g)
Dia|Day
Hora|Hour
Peso|Weight
Dia do perfil|Profile day
Peso semanal|Weekly weight
Peso horário|Hourly weight
Massa alocada (g)|Allocated mass (g)
Emissões por fonte|Emissions by source
Emissões por célula|Emissions per cell
Balanço espacial|Spatial balance
Grade utilizada|Grid used
Inventário em grade|Gridded inventory
Metadados NetCDF|NetCDF metadata
Perfis e resumos|Profiles and summaries
Alocação relativa|Relative allocation
Projeção anual|Annual projection
Resumo mensal|Monthly summary
original|original
especiada|speciated
gráfico por poluente|chart by pollutant
Planilha padronizada da importação.|Standardized imported spreadsheet.
Massa por atividade, fonte e poluente.|Mass by activity, source, and pollutant.
Totais em gramas por poluente.|Totals in grams by pollutant.
Fatores, unidades e referências.|Factors, units, and references.
Seleções, totais e avisos da execução.|Run selections, totals, and notices.
Massa por espécie e origem.|Mass by species and origin.
Totais com origem química explícita.|Totals with chemical origin identified.
Frações, massas moleculares quando disponíveis e referência.|Fractions, available molecular weights, and reference.
Massas originais, derivadas e residuais, com avisos.|Original, allocated, and residual masses with notices.
Documento em português com resultados, fatores e etapas executadas.|Portuguese document with results, factors, and completed stages.
Identificação, metodologia, totais e alertas.|Identification, methodology, totals, and alerts.
Massas, coordenadas e situação espacial.|Masses, coordinates, and spatial status.
Massas em células da grade GeoJSON.|Masses in GeoJSON grid cells.
Geometria de células do domínio informado.|Cell geometry of the supplied domain.
Massas mapeadas, fora da grade e casos ambíguos.|Mapped masses, off-grid masses, and ambiguous cases.
Massas por série e território, inclusive casos sem atribuição.|Masses by series and territory, including unassigned cases.
Pesos de 24, 7 e 168 intervalos, referência e massas-base.|Weights for 24, 7, and 168 intervals, reference, and base masses.
Massa por fonte nos 168 intervalos sem calendário.|Mass by source across 168 intervals without a calendar.
Massas horárias por série no domínio WRF, no relógio do perfil.|Hourly masses by series in the WRF domain using the profile time reference.
Massas acumuladas por mês e série no domínio WRF.|Accumulated masses by month and series in the WRF domain.
NetCDF intermediário com massa em células e projeção anual quando disponível.|Intermediate NetCDF with cell mass and annual projection when available.
Grade, calendário e balanços de massa por série.|Grid, calendar, and mass balances by series.
`.trim().split("\n").map(line => line.split("|")));
englishPatterns.push(
    ["{} {} · Gerado sob demanda", "{1} {2} · Generated on demand"],
    ["{} {} · {} KiB", "{1} {2} · {3} KiB"],
    ["{} {} · {} MiB", "{1} {2} · {3} MiB"],
    ["{} {} · {} B", "{1} {2} · {3} B"],
    ["Total: {}", "Total: {1}"],
    ["Média: {}", "Mean: {1}"],
    ["Maior fonte: {}", "Largest source: {1}"],
    ["{} fontes", "{1} sources"],
    ["{} fonte", "{1} source"],
    ["{} registros", "{1} records"],
    ["{} registro", "{1} record"],
    ["{} registro(s)", "{1} record(s)"],
    ["{} fontes sem UF na base selecionada", "{1} sources without a state in the selected basis"],
    ["Participação no total classificado no Brasil: {}", "Share of total assigned to Brazilian states: {1}"],
    ["Potência informada: {} MW", "Reported power: {1} MW"],
    ["Consumo: {} GJ", "Consumption: {1} GJ"],
    ["Consultar as {} fontes nesta coordenada", "View the {1} sources at this coordinate"],
    ["Preenchimento das UFs: massa total · {}.", "State fill: total mass · {1}."],
    ["Base: {}. Perfil relativo sem calendário. Em unidades de massa, os valores são alocações modeladas, sem taxa horária. Os perfis de 24 e 7 intervalos são marginais.", "Basis: {1}. Relative profile without a calendar. Mass values are modeled allocations, not hourly rates. The 24- and 7-interval profiles are marginal."],
    ["Domínio {} · {} × {} · {} × {} m projetados. {} horas ({}). Massas horárias para os pares série/célula ativos.", "Domain {1} · {2} × {3} · {4} × {5} projected m. {6} hours ({7}). Hourly masses for active series/cell pairs."],
    ["{} · {} fontes · {} g no inventário. {} g mapeados, {} g fora da grade, {} g em interseções ambíguas e {} g com coordenadas inválidas.", "{1} · {2} sources · {3} g in inventory. {4} g mapped, {5} g outside grid, {6} g in ambiguous intersections, and {7} g with invalid coordinates."]
);

englishUI.push(...`
Mapa interativo de fontes emissoras|Interactive map of emission sources
A planilha não possui dados.|The spreadsheet has no data.
A planilha não possui linhas de dados.|The spreadsheet has no data rows.
A planilha contém cabeçalhos vazios.|The spreadsheet contains empty headers.
Existem cabeçalhos repetidos após a normalização.|Duplicate headers remain after normalization.
Uma coluna foi associada a mais de um campo.|One column was associated with more than one field.
Formato não suportado. Envie CSV, TXT ou XLSX.|Unsupported format. Upload CSV, TXT, or XLSX.
Não foi possível importar o arquivo.|Could not import the file.
Resposta inválida do servidor.|Invalid server response.
Não foi possível conectar ao servidor.|Could not connect to the server.
Planilha importada e validada com sucesso!|Spreadsheet imported and validated successfully!
Foram identificados problemas na planilha:|The spreadsheet has validation issues:
Os arquivos disponíveis em disco já excedem 256 MiB descompactados. Selecione menos arquivos.|The available files on disk already exceed 256 MiB uncompressed. Select fewer files.
O ZIP aceita até 64 arquivos. Selecione menos arquivos.|The ZIP supports up to 64 files. Select fewer files.
Variante de figura indisponível para esta execução.|Figure variant unavailable for this run.
`.trim().split("\n").map(line => line.split("|")));
englishPatterns.push(
    ["Colunas obrigatórias não identificadas: {}", "Required columns not found: {1}"],
    ["Colunas adicionais ignoradas: {}", "Extra columns ignored: {1}"],
    ["Mais de uma coluna corresponde a '{}': {}", "More than one column matches '{1}': {2}"],
    ["{}: {} valor(es) ausente(s). Linhas: {}.", "{1}: {2} missing value(s). Rows: {3}."],
    ["{}: valor numérico inválido. Linhas: {}. Utilize ponto decimal.", "{1}: invalid numeric value. Rows: {2}. Use a decimal point."],
    ["{}: valor fora do intervalo esperado. Linhas: {}.", "{1}: value outside the expected range. Rows: {2}."],
    ["year: informe um ano entre {} e {}. Linhas: {}.", "year: enter a year between {1} and {2}. Rows: {3}."],
    ["Célula {}", "Cell {1}"]
);

englishUI.push(...`
Escolha uma referência|Choose a reference
Execução atual|Current run
Nenhum combustível deste ano é suportado pelo setor selecionado.|The selected sector supports no fuel for this year.
Selecione setor, ano e combustível.|Select a sector, year, and fuel.
Classificação territorial|Territorial classification
UF (código)|State (code)
Massas da base por célula.|Base masses per cell.
Massas horárias recuperáveis a partir da massa por célula e dos pesos horários.|Hourly masses can be reconstructed from cell masses and hourly weights.
% da seleção|% of selection
Figura indisponível para esta seleção.|Figure unavailable for this selection.
Sudeste|Southeast
Nordeste|Northeast
Centro-Oeste|Central-West
Sul|South
Norte|North
`.trim().split("\n").map(line => line.split("|")));
englishPatterns.push(
    ["Referência para {}", "Reference for {1}"],
    ["{}: as frações do perfil somam {}. O saldo de massa não foi redistribuído.", "{1}: profile fractions sum to {2}. Residual mass was not redistributed."],
    ["Somas dos pesos: horário bruto {}, horário normalizado {}, semanal {}, combinado {}. Os 168 intervalos repartem a massa da base sem calendário.", "Weight sums: raw hourly {1}, normalized hourly {2}, weekly {3}, combined {4}. The 168 intervals allocate base mass without a calendar."],
    ["Domínio {} · {} × {} · {} × {} m projetados. Massas da base por célula.", "Domain {1} · {2} × {3} · {4} × {5} projected m. Base masses per cell."],
    ["Domínio {} · {} × {} · {} × {} m projetados. {} horas ({}). Massas horárias recuperáveis a partir da massa por célula e dos pesos horários.", "Domain {1} · {2} × {3} · {4} × {5} projected m. {6} hours ({7}). Hourly masses can be reconstructed from cell masses and hourly weights."],
    ["Exibindo as {} maiores fontes de {}. Indicadores usam toda a seleção.", "Showing the {1} largest sources out of {2}. Indicators use the full selection."]
);
