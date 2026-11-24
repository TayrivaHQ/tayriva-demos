# NFS-e em escala: dez milhões de notas simuladas

**Laboratório educacional com dados 100% sintéticos. Não emite, não autoriza e não valida documentos fiscais. Não use para apuração, recolhimento ou decisões fiscais.**

Comece pela [planilha portátil `rtc-nfse.tay`](rtc-nfse.tay). Abra no Tayriva **v0.14.0** ou posterior, selecione **Consulta!B11** e use **Review → Explain & Review**. Esse snapshot de uma nota é fixo e funciona sem Java, SQLite externo ou internet. Veja também o [PDF demonstrativo](danfse-demonstrativo.pdf) e a [memória oficial da nota 10.000.000](nota-10000000.json), com os corpos de entrada e saída das duas chamadas.

**648× mais rápido que a calculadora de referência da própria Receita Federal.** Em um benchmark separado, a versão de desenvolvimento do Tayriva calculou e gravou 10 milhões de notas sintéticas em 34,30 segundos, contra 6 horas, 10 minutos e 28 segundos do motor oficial em Java. Todos os valores coincidiram, centavo a centavo, nos quatro cenários testados. [Veja o benchmark e a metodologia](benchmark/matched-10m.md).

## Calcule no Tayriva

O [benchmark com quatro tratamentos](mixed/README.md) aplica uma tabela de regras da planilha e compara os resultados linha a linha com o motor oficial. O [demo de cálculo nativo da planilha](native/README.md) usa as fórmulas do Tayriva para calcular cada nota e gravar o lote no SQLite. O cenário original descrito abaixo continua disponível como referência do motor oficial.

## O que realmente foi calculado

Para medir cada nota separadamente, sem reutilizar resultados, use [o benchmark por nota](benchmark/README.md). O teste rápido descrito abaixo mede o fluxo que reaproveita perfis, não esse benchmark.

O SQLite grava **10.000.000 de notas sintéticas e 10.000.000 de linhas de resultado**. São cem perfis monetários distintos do mesmo cenário educacional (NBS 122011200, CST 200, cClassTrib 200028, Porto Alegre, 10 de março de 2027). O motor oficial é chamado **duas vezes por perfil distinto**: base unificada NFS-e e tributos com observabilidade. O lote reutiliza esses cem resultados e grava cada nota por chave primária. **Não são dez milhões de chamadas à API, dez milhões de perfis distintos nem um benchmark de notas reais.**

Em um teste local Linux x86-64, o verificador completo terminou em **22,6 s** após iniciar a API oficial, incluindo geração, as chamadas para cem perfis, escrita das linhas, interrupção/retomada, reexecução idempotente, verificações SQLite e abertura da planilha. O SQLite final ocupou **952 MiB**. O tempo exclui baixar, compilar e iniciar o motor e não representa desempenho com dez milhões de chamadas.

A base de R$ 1.370,67 da nota 10.000.000 retornou CBS de R$ 48,25, IBS estadual de R$ 0,27 e IBS municipal de R$ 0,27, totalizando R$ 48,79 de CBS + IBS. As alíquotas nominais de **8,80%, 0,05% e 0,05%** são entradas ilustrativas do [exemplo oficial](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular/blob/f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4/docs/exemplos.md), **não** alíquotas efetivas ou oficiais de 2027. O motor devolve `CALCULO_SIMULADO`. Este recorte não simula todo o universo de NFS-e, Simples Nacional, retenção, emissão, validação fiscal ou demais regimes.

## Executar o laboratório local

Use Python 3.11+, Tayriva v0.14.0 Linux ([pacote server](https://github.com/TayrivaHQ/tayriva/releases/download/v0.14.0/tayriva-0.14.0-linux-x86_64-server.tar.gz)) e Java 25. Separe ao menos 2 GB para o banco e arquivos de trabalho. Na primeira preparação o Maven precisa baixar dependências.

Em um terminal, configure a implementação original **Receita Federal RTC 1.7.2, base V0073**:

```sh
git clone https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git
cd calculadora-rtc-regime-regular
git checkout f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4
mkdir -p calculadora/db
./mvnw flyway:migrate -Dflyway.configFiles=./flyway/flyway-pro.conf --batch-mode
SERVER_PORT=18927 SERVER_ADDRESS=127.0.0.1 ./mvnw spring-boot:run -Dspring-boot.run.profiles=offline
```

No clone dos demos, em outro terminal:

```sh
demo=./receita/demo.py
db="$PWD/rtc.sqlite"
server=/caminho/para/o/pacote/tayriva
python3 "$demo" init --db "$db"                              # 10.000.000; use --total 2000 para um teste rápido
python3 "$demo" bulk --db "$db" --max-chunks 2              # para após dois lotes, ou quando não houver mais notas
python3 "$demo" bulk --db "$db"                             # retoma do último lote confirmado
python3 "$demo" workbook --db "$db" --server "$server" --output ./rtc-consulta.tay
python3 "$demo" invoice --db "$db" --number 1 --pdf ./nota-1-demonstrativa.pdf > ./nota-1-memoria.json
```

Abra `rtc-consulta.tay` no Tayriva e edite **Consulta!B4** para trocar a nota. Use **Explain & Review** em **B11**, siga as dependências para a aba **Fonte SQL**, e inspecione os valores das entradas e as consultas SQLite parametrizadas. O Review captura os resultados e a consulta; não executa novamente a SQL e não incorpora todas as linhas do banco. O comando `invoice` recupera a linha e a versão do motor, além dos quatro corpos JSON (base/tributos, entrada/saída) para auditoria. O PDF, também gerado por esse comando, é apenas demonstrativo: não tem QR, chave, assinatura nem protocolo.

O banco tem tabelas separadas `invoices` (entradas), `scenarios` (memória do motor por perfil), `tax_results` (um resultado por nota) e `state` (progresso). Cada lote grava resultados e checkpoint na mesma transação; refazer o comando não duplica notas. Não edite diretamente os dados gerados; crie uma base nova para outros parâmetros. O arquivo `.tay` vinculado guarda o caminho absoluto para o SQLite; regenere o workbook se mudar o banco de lugar. O Tayriva consulta o banco; o script separado é quem executa o motor, escreve os lotes e gera o PDF. O Tayriva MCP não abre a variante com conexão externa; use o snapshot portátil no MCP.

Para repetir a verificação integral, mantenha a API oficial local e rode:

```sh
python3 receita/verify.py --server "$server" --total 10000000 --directory ./rtc-verificacao
```

Motor original: [Receita Federal, código-fonte e instruções](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular/tree/f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4), [licença MIT](LICENSE-RECEITA-FEDERAL), [anúncio oficial do código aberto](https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/novembro/receita-federal-publica-primeiro-codigo-fonte-aberto-no-github-e-amplia-transparencia-da-reforma-tributaria/). A Receita não desenvolveu nem certificou este demo.
