exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
import cProfile,pstats
axis=np.arange(-128.,129.,2.);xx,yy=np.meshgrid(axis,axis);la,lo,_=fr.enu_to_geodetic(xx,yy,0.)
natural=raw(la,lo);prof=cProfile.Profile();t=time.perf_counter();prof.enable()
z=gr.apply(la,lo,natural,.04);prof.disable()
print('cold',time.perf_counter()-t,flush=True);prof.dump_stats('.work-uk/grading-profile.prof')
print('bounds',[(k,len(v)) for k,v in gr.uk_vertical.cache.items()],flush=True)
print('plans',sorted([(fid,tuple(p.xy.min(0)),tuple(p.xy.max(0))) for row in gr.base_cells.values() for fid,p in row],key=lambda v:max(np.array(v[2])-v[1]),reverse=True)[:5],flush=True)
pstats.Stats(prof).sort_stats('cumulative').print_stats(38)
for j in range(2):
 t=time.perf_counter();gr.apply(la,lo,natural,.04);print('warm',time.perf_counter()-t,flush=True)
md.close();dd.pool.shutdown();dd.urgent_pool.shutdown()
