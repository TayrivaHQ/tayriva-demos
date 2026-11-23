# Benchmark sem reutilização por nota

Este benchmark é **separado** do demo rápido que reaproveita 100 perfis. Aqui **cada nota é lida do SQLite, calculada pelos serviços oficiais da Receita e gravada de volta pelo seu próprio ID**. Não agrupamos notas, não usamos resultados anteriores e não calculamos uma nota para replicar em outras. A implementação oficial continua usando seus próprios caches de dados de referência (por exemplo, a classificação tributária); não há cache de valores de notas no adaptador.

O gerador produz dez milhões de combinações monetárias distintas: o valor bruto usa um módulo de 10.000.019, coprimo com o multiplicador, em um intervalo de até dez milhões de IDs. Datas e horários cobrem 2027; municípios alternam entre São Paulo, Rio de Janeiro, Belo Horizonte e Porto Alegre. Descontos, ISSQN e alíquotas nominais ilustrativas variam deterministicamente. O recorte continua sendo um serviço educacional com NBS `122011200`, CST `200` e cClassTrib `200028`; não representa diversidade de produtos, de tributações ou de documentos reais.

O Java incorpora o motor fixado **1.7.2 / V0073**, commit [`f1eebd7c`](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular/tree/f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4). Para cada nota ele chama `BaseCalculoUnificadaNfseService.calcular` e `ObservabilidadeService.processarOperacao`, os mesmos serviços usados pela API REST. Não há chamadas HTTP por nota na passagem medida. O validador independente chama os endpoints REST oficiais, fora da medição, para comparar cinco campos monetários nas amostras distribuídas, inclusive a primeira e a última. O motor usa as regras do regime geral com alíquotas sintéticas; todos os itens válidos têm estado `CALCULO_SIMULADO`.

## Reproduzir

Abra [o workflow no GitHub Actions](https://github.com/TayrivaHQ/tayriva-demos/actions/workflows/receita-per-invoice.yml), ou execute em um clone com Java 25, Python 3.11+, acesso Maven e espaço livre para o banco. Use caminhos absolutos:

```sh
demo="$PWD"
db="$PWD/bench-invoices.sqlite"
git clone https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git
cd calculadora-rtc-regime-regular
git checkout --detach f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4
mkdir -p calculadora/db src/main/java/benchmark
cp "$demo/receita/benchmark/Bench.java" src/main/java/benchmark/
./mvnw --batch-mode flyway:migrate -Dflyway.configFiles=./flyway/flyway-pro.conf
python3 "$demo/receita/benchmark/dataset.py" prepare "$db" --rows 10000000
RTC_BENCH_DB="$db" RTC_BENCH_WORKERS=4 SERVER_ADDRESS=127.0.0.1 SERVER_PORT=18929 \
  ./mvnw --batch-mode spring-boot:run -Dspring-boot.run.main-class=benchmark.Bench \
  -Dspring-boot.run.profiles=offline \
  '-Dspring-boot.run.jvmArguments=-Xmx2g -Dspring.devtools.restart.enabled=false'
```

Em seguida, inicie a API REST local conforme o [README do demo](../README.md) e rode:

```sh
python3 "$demo/receita/benchmark/dataset.py" verify "$db" --rows 10000000
```

O cronômetro inicia imediatamente antes de abrir a transação e preparar a primeira leitura; termina após o último `commit`. Leitura, cálculo e escrita mais commit são fases sequenciais por página de 4.096 notas. Apenas o cálculo dentro da página é paralelo e o número de trabalhadores é explícito. A passagem usa `journal_mode=DELETE` e `synchronous=FULL`, com marcador de progresso na mesma transação da gravação. Qualquer erro interrompe a execução com código não zero; não pula linhas. A geração, compilação, inicialização Spring, migração e validação posterior ficam fora desse tempo. A verificação confere contagem, IDs inicial/final, integridade SQLite, chaves estrangeiras, totais e paridade de amostras com a API.

Cada execução do workflow publica somente os relatórios de ambiente, geração, medição e validação, não o banco. Uma execução retomada pode completar o banco, mas não conta como a medição limpa de ponta a ponta: o workflow exige `start_row=0` e o número pedido de linhas efetivamente calculadas.
