import sys,cProfile,pstats,faulthandler

sys.path[:0]=['server'];import geodesy,mapdata,netfetch,grading,dem,numpy as np
cache='C:/Users/topge/.cache/beamng-earth';net=netfetch.Fetcher(offline=True);md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net);fr=geodesy.EnuFrame(51.4927,-.1204);g=grading.Grader(fr,md,lambda la,lo:dd.sample(la,lo,15));X,Y=np.meshgrid(np.arange(-512.,513.,16.),np.arange(-512.,513.,16.));la,lo,_=fr.enu_to_geodetic(X,Y,0.);base=dd.sample(la,lo,15)
p=cProfile.Profile();p.enable();out=g.apply(la,lo,base,.04);p.disable();p.dump_stats('.work-uk/world-grade-profile.prof');pstats.Stats(p).strip_dirs().sort_stats('cumtime').print_stats(24);md.close();dd.pool.shutdown()
