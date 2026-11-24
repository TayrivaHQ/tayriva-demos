#!/usr/bin/env bash
# Sequential, local, one-core comparison; preparing binaries/data is outside the timer.
set -euo pipefail
demos="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${RTC_RESULTS:?Directory containing mixed-native-10m.sqlite and mixed-official-10m.sqlite}"
: "${RTC_TAYRIVA_SERVER:?Path to the Tayriva binary or launcher}"
: "${RTC_OFFICIAL_CHECKOUT:?Pinned official checkout with dependencies preloaded and its offline DB built}"
: "${RTC_CPU:?One logical CPU available to taskset}"
rows="${RTC_ROWS:-10000000}"
d="$(realpath "$RTC_RESULTS")"
mkdir -p "$d/tmp"
export TMPDIR="$d/tmp" SQLITE_TMPDIR="$d/tmp"
: "${JAVA_HOME:?Set JAVA_HOME to your JDK 25 distribution}"
export PATH="$JAVA_HOME/bin:$PATH" JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$d/tmp"
native="$d/mixed-native-10m.sqlite"
official="$d/mixed-official-10m.sqlite"
workbook="$d/mixed-native-10m.tay"
export SERVER_ADDRESS=127.0.0.1 SERVER_PORT=18929 RTC_BENCH_WORKERS=1 RTC_BENCH_ATOMIC=1 RTC_BENCH_DB="$official"

# One run at a time, with explicit records even if startup or validation fails.
exec 9>"$d/pair.lock"
flock -n 9 || { echo "Another scheduled benchmark holds the lock" >&2; exit 1; }
echo "$$" > "$d/pair.pid"
trap 'code=$?; echo "$code" > "$d/pair-exit"; date -Is >> "$d/pair-stage.log"' EXIT
resume="${RTC_OFFICIAL_ONLY:-0}"
if [[ "$resume" == 1 ]]; then
    # An interrupted atomic Java run has no checkpoint. Keep the completed
    # native measurement and rerun only Java from the beginning.
    test ! -s "$d/pair-official.json"
    python3 - "$d/pair-native.json" "$official" "$rows" <<'PYRESUME'
import json, sqlite3, sys
assert json.load(open(sys.argv[1]))["rows"]==int(sys.argv[3])
with sqlite3.connect(sys.argv[2]) as db:
    state=db.execute("SELECT total, committed FROM bench_state").fetchone()
    assert state==(int(sys.argv[3]),0), state
PYRESUME
    if [[ -f "$d/pair-official.log" ]]; then
        cp "$d/pair-official.log" "$d/pair-official-interrupted-$(date +%s).log"
    fi
    rm -f "$d/pair-exit" # this run now owns the lock
else
    test ! -e "$d/pair-native.json"
    cmp -s "$native" "$official" || { echo "Benchmark input files are not byte-identical." >&2; exit 1; }
fi

mkdir -p "$RTC_OFFICIAL_CHECKOUT/src/main/java/benchmark"
test "$(git -C "$RTC_OFFICIAL_CHECKOUT" rev-parse HEAD)" = f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4
git -C "$RTC_OFFICIAL_CHECKOUT" diff --quiet HEAD --
cp "$demos/receita/benchmark/Bench.java" "$RTC_OFFICIAL_CHECKOUT/src/main/java/benchmark/"
if [[ "$resume" != 1 ]]; then
    {
        date -Is
        printf 'CPU pin: %s\nSource official: ' "$RTC_CPU"
        git -C "$RTC_OFFICIAL_CHECKOUT" rev-parse HEAD
        sha256sum "$RTC_TAYRIVA_SERVER"
        lscpu
        java -version
    } >"$d/pair-environment.txt" 2>&1
    printf '%s native start\n' "$(date -Is)" >>"$d/pair-stage.log"
    test -f "$workbook" || python3 "$demos/receita/mixed/workbook.py" build --server "$RTC_TAYRIVA_SERVER" --db "$native" --workbook "$workbook"
    taskset -c "$RTC_CPU" python3 "$demos/receita/mixed/workbook.py" run --server "$RTC_TAYRIVA_SERVER" --db "$native" --workbook "$workbook" | tee "$d/pair-native.json"
    python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["rows"]==int(sys.argv[2])' "$d/pair-native.json" "$rows"
    python3 "$demos/receita/mixed/workbook.py" review --server "$RTC_TAYRIVA_SERVER" --db "$native" --workbook "$workbook" >"$d/pair-review.json"
fi
printf '%s official startup\n' "$(date -Is)" >>"$d/pair-stage.log"
cd "$RTC_OFFICIAL_CHECKOUT"
taskset -c "$RTC_CPU" ./mvnw --offline --batch-mode spring-boot:run \
    -Dspring-boot.run.main-class=benchmark.Bench -Dspring-boot.run.profiles=offline \
    '-Dspring-boot.run.jvmArguments=-Xmx2g -XX:ActiveProcessorCount=1 -Dspring.devtools.restart.enabled=false' \
    >"$d/pair-official.log" 2>&1
sed -n 's/^RTC_BENCH //p' "$d/pair-official.log" >"$d/pair-official.json"
python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["start_row"]==0 and r["last_row"]==r["rows"]==int(sys.argv[2]) and r["errors"]==0 and r["atomic"] and r["workers"]==1, r' "$d/pair-official.json" "$rows"
printf '%s comparing complete SQLite output files\n' "$(date -Is)" >>"$d/pair-stage.log"
python3 "$demos/receita/mixed/dataset.py" compare "$native" --official "$official" --rows "$rows" | tee "$d/pair-parity.json"
printf '%s finished with verified parity\n' "$(date -Is)" >>"$d/pair-stage.log"
