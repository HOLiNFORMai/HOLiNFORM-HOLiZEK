"""HOLiZEK V1, Windows GUI and import CLI."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from holizek.paths import root_path


def main(argv=None):
    parser=argparse.ArgumentParser(description='HOLiZEK recipe catalog')
    parser.add_argument('--root',help='HOLiNFORM root; otherwise HOLINFORM_ROOT/global.json')
    parser.add_argument('--mode',choices=['local','server'],default='local',help='Explicit SQLite/PostgreSQL mode')
    parser.add_argument('--import-xlsx',type=Path,metavar='FILE')
    parser.add_argument('--sync-images',action='store_true')
    parser.add_argument('--stats',action='store_true')
    parser.add_argument('--images-from',type=Path,help='Alternative root with haztartas_ma_export/images subfolder')
    args=parser.parse_args(argv)
    root=root_path(args.root)
    if args.import_xlsx or args.sync_images or args.stats:
        from holizek.database import CatalogDB
        from holizek.media import synchronize_images
        db=CatalogDB(root,args.mode)
        try:
            if args.import_xlsx:
                result=db.import_workbook(args.import_xlsx,lambda msg,n,t: print(f'\r{msg}: {n}/{t}',end='',flush=True))
                print('\n'+json.dumps(result,ensure_ascii=False))
            if args.sync_images:
                result=synchronize_images(db,args.images_from,lambda msg,n,t: print(f'\r{msg}: {n}/{t}',end='',flush=True))
                print('\n'+json.dumps(result,ensure_ascii=False))
            if args.stats:
                print(json.dumps({'backend':db.status_label,'recipes':db.count(),'images':db.count('recipe_images'),
                    'categories':len(db.categories())},ensure_ascii=False))
        finally:db.close()
        return
    from holizek.gui import Application
    Application(root,args.mode).mainloop()


if __name__=='__main__':
    main()
