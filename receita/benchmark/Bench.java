package benchmark;

import java.math.BigDecimal;
import java.sql.*;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.*;
import br.gov.serpro.rtc.CalculadoraTributoApplication;
import br.gov.serpro.rtc.api.model.input.*;
import br.gov.serpro.rtc.api.model.input.basecalculo.BaseCalculoUnificadaNfseInput;
import br.gov.serpro.rtc.api.model.input.basecalculo.enumeration.OpcaoSimplesNacional;
import br.gov.serpro.rtc.api.model.input.basecalculo.enumeration.SituacaoOperacaoNfse;
import br.gov.serpro.rtc.domain.model.enumeration.EstadoItemEnum;
import br.gov.serpro.rtc.domain.service.ObservabilidadeService;
import br.gov.serpro.rtc.domain.service.basecalculo.BaseCalculoUnificadaNfseService;
import org.springframework.boot.SpringApplication;

public class Bench {
    record Invoice(long id,long gross,long discount,long iss,String event,long municipality,
                   String uf,String nbs,String cst,String code,int cbs,int state,int city) {}
    record Tax(long id,long base,long cbs,long state,long city,long ibs) {}
    private static final int PAGE = 4096;
    private static final BigDecimal decimal(long cents) {
        return BigDecimal.valueOf(cents,2);
    }
    private static final long cents(BigDecimal value) {
        // The official model already rounds these monetary fields to cents.
        return value.movePointRight(2).longValueExact();
    }
    private static String zeroPad(String s, int n) {
        return s.length() >= n ? s : "0".repeat(n-s.length()) + s;
    }
    static Tax calculate(Invoice i, BaseCalculoUnificadaNfseService base, ObservabilidadeService tax) {
        try {
            var event=OffsetDateTime.parse(i.event);
            var bi=new BaseCalculoUnificadaNfseInput();
            bi.setAnoFatoGerador(event.getYear());
            bi.setOpSimpNac(OpcaoSimplesNacional.NAO_OPTANTE);
            bi.setSituacao(SituacaoOperacaoNfse.COMUM);
            bi.setVServ(decimal(i.gross)); bi.setVDescIncond(decimal(i.discount)); bi.setVISSQN(decimal(i.iss));
            var b=base.calcular(bi);
            if (!b.getErros().isEmpty() || b.getBaseRG()==null)
                throw new IllegalStateException("Official base service rejected input: "+b.getErros());
            var rates=new AliquotasNominaisInput();
            rates.setCbs(decimal(i.cbs)); rates.setIbsEstadual(decimal(i.state)); rates.setIbsMunicipal(decimal(i.city));
            var item=new ItemOperacaoInput();
            item.setNumero(1); item.setNbs(i.nbs); item.setCst(i.cst); item.setCClassTrib(i.code);
            item.setBaseCalculo(b.getBaseRG()); item.setAliquotasNominais(rates);
            var request=new OperacaoInput();
            request.setId("rtc-bench-"+i.id);
            request.setVersao("1.0.0"); request.setDhFatoGerador(event);
            request.setMunicipio(i.municipality); request.setUf(i.uf);
            request.setItens(List.of(item));
            var output=tax.processarOperacao(request,"http://127.0.0.1/api").getObjetos().getFirst();
            if (output.getEstadoItem()!=EstadoItemEnum.CALCULO_SIMULADO)
                throw new IllegalStateException("Official tax service rejected input: "+output.getErros());
            var g=output.getTribCalc().getGrupoIBSCBS();
            return new Tax(i.id,cents(g.getVBC()),cents(g.getGCBS().getVCBS()),
                    cents(g.getGIBSUF().getVIBSUF()),cents(g.getGIBSMun().getVIBSMun()),cents(g.getVIBS()));
        } catch (RuntimeException e) {
            throw new IllegalStateException("Invoice "+i.id+" was not calculated", e);
        }
    }
    public static void main(String[] args) throws Exception {
        String path=System.getenv("RTC_BENCH_DB");
        if (path==null || path.isEmpty()) throw new IllegalArgumentException("Set RTC_BENCH_DB");
        int workers=Integer.parseInt(System.getenv().getOrDefault("RTC_BENCH_WORKERS","4"));
        if (workers<1 || workers>16) throw new IllegalArgumentException("Use 1..16 workers");
        boolean atomic="1".equals(System.getenv("RTC_BENCH_ATOMIC"));
        // The web context initializes exactly the same official beans as the reference REST API;
        // no invoice traverses HTTP in the timed pass.
        try (var ctx=SpringApplication.run(CalculadoraTributoApplication.class,args);
             var db=DriverManager.getConnection("jdbc:sqlite:"+path);
             var pool=Executors.newFixedThreadPool(workers)) {
            var base=ctx.getBean(BaseCalculoUnificadaNfseService.class);
            var tax=ctx.getBean(ObservabilidadeService.class);
            try (var s=db.createStatement()) {
                s.execute("PRAGMA journal_mode=DELETE");
                s.execute("PRAGMA synchronous=FULL");
                s.execute("PRAGMA foreign_keys=ON");
                s.execute("PRAGMA busy_timeout=30000");
            }
            long total, committed;
            try (var s=db.createStatement();
                 var r=s.executeQuery("SELECT total,committed FROM bench_state WHERE id=1")) {
                if (!r.next()) throw new IllegalStateException("Prepare benchmark dataset first");
                total=r.getLong(1); committed=r.getLong(2);
            }
            var startRow=committed;
            if (atomic && committed!=0) throw new IllegalStateException("Atomic mode requires a fresh benchmark copy");
            long readNs=0, calcNs=0, commitNs=0;
            long start=System.nanoTime();
            db.setAutoCommit(false);
            if (atomic) try (var clear=db.createStatement()) {
                var clock=System.nanoTime();
                clear.executeUpdate("DELETE FROM bench_results");
                commitNs+=System.nanoTime()-clock;
            }
            long nextProgress=10000;
            try (var select=db.prepareStatement("SELECT * FROM bench_invoices WHERE id>? ORDER BY id LIMIT ?");
                 var write=db.prepareStatement("INSERT INTO bench_results VALUES (?,?,?,?,?,?)");
                 var cp=db.prepareStatement("UPDATE bench_state SET committed=? WHERE id=1")) {
                while (committed<total) {
                    long clock=System.nanoTime();
                    var data=new ArrayList<Invoice>(PAGE);
                    select.setLong(1,committed); select.setInt(2,PAGE);
                    try (var r=select.executeQuery()) {
                        while (r.next()) data.add(new Invoice(r.getLong(1),r.getLong(2),r.getLong(3),r.getLong(4),
                            r.getString(5),r.getLong(6),r.getString(7),r.getString(8),zeroPad(r.getString(9),3),zeroPad(r.getString(10),6),
                            r.getInt(11),r.getInt(12),r.getInt(13)));
                    }
                    if (data.size()!=Math.min(PAGE,total-committed) || data.getFirst().id!=committed+1
                            || data.getLast().id!=committed+data.size())
                        throw new IllegalStateException("Input IDs not contiguous");
                    readNs+=System.nanoTime()-clock;
                    clock=System.nanoTime();
                    Tax[] results=new Tax[data.size()];
                    var tasks=new ArrayList<Callable<Void>>();
                    for (int w=0; w<workers; w++) {
                        int lo=w*data.size()/workers, hi=(w+1)*data.size()/workers;
                        tasks.add(()->{for(int j=lo;j<hi;j++) results[j]=calculate(data.get(j),base,tax); return null;});
                    }
                    for (var f:pool.invokeAll(tasks)) f.get();
                    calcNs+=System.nanoTime()-clock;
                    clock=System.nanoTime();
                    for (Tax t:results) {
                        write.setLong(1,t.id); write.setLong(2,t.base); write.setLong(3,t.cbs);
                        write.setLong(4,t.state); write.setLong(5,t.city); write.setLong(6,t.ibs); write.addBatch();
                    }
                    for (int n:write.executeBatch()) if (n!=1) throw new IllegalStateException("Unwritten tax row");
                    write.clearBatch();
                    committed+=results.length;
                    if (!atomic) {
                        cp.setLong(1,committed); cp.executeUpdate();
                        db.commit();
                    }
                    commitNs+=System.nanoTime()-clock;
                    if (committed>=nextProgress || committed==total) {
                        System.out.printf(Locale.ROOT,"RTC_PROGRESS %d/%d %.3fs (%s)%n",committed,total,(System.nanoTime()-start)/1e9,
                            atomic ? "calculated; pending atomic commit" : "committed");
                        nextProgress=committed+(committed<100000 ? 10000 : 100000);
                    }
                }
                if (atomic) {
                    var clock=System.nanoTime();
                    cp.setLong(1,committed); cp.executeUpdate();
                    db.commit();
                    commitNs+=System.nanoTime()-clock;
                }
            }
            long elapsed=System.nanoTime()-start;
            System.out.printf(Locale.ROOT,"RTC_BENCH {\"start_row\":%d,\"last_row\":%d,\"rows\":%d,\"errors\":0,"
                +"\"workers\":%d,\"atomic\":%b,\"page\":%d,\"elapsed_s\":%.6f,\"read_s\":%.6f,\"calculate_s\":%.6f,\"write_commit_s\":%.6f}%n",
                startRow,committed,committed-startRow,workers,atomic,PAGE,elapsed/1e9,readNs/1e9,calcNs/1e9,commitNs/1e9);
        }
    }
}
