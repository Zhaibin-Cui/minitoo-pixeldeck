"""Audit and package an explicit public file set. Never uploads or pushes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES={'src','tests','docs','examples','tools','.github'}
FILES={'README.md','LICENSE','CONTRIBUTING.md','CHANGELOG.md','pyproject.toml','run.py','launch.ps1','.gitignore','.gitattributes'}
BINARY={'.png','.gif','.wav'}
TEXT={'.py','.md','.toml','.json','.cs','.ps1','.yml','.yaml','.txt'}
PATTERNS={
    'user path':re.compile(r'(?:[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]|/(?:Users|home)/[a-z0-9_-]+/)',re.I),
    'device address':re.compile(r'\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b',re.I),
    'access token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})\b'),
}

def selected_files():
    for path in sorted(ROOT.rglob('*')):
        relative=path.relative_to(ROOT)
        if relative.parts[0] not in DIRECTORIES and relative.as_posix() not in FILES: continue
        if any(p in {'__pycache__','bin','.venv'} or p.endswith('.egg-info') for p in relative.parts): continue
        if not path.is_file(): continue
        if path.suffix not in BINARY|TEXT and relative.as_posix() not in FILES: continue
        if path.name.endswith('.local.json') or path.name.startswith('.env'): continue
        if path.is_symlink(): raise ValueError('Symlink is not a public release file: '+str(relative))
        yield path,relative.as_posix()

def audit(files,terms=()):
    errors=[]; included={name for _,name in files}
    for path,name in files:
        if path.suffix in BINARY:
            if path.suffix in {'.png','.gif'}:
                from PIL import Image
                with Image.open(path) as image:
                    if any(key in image.info for key in ('exif','comment','Author','Description')):
                        errors.append(name+': unexpected image metadata')
            continue
        content=path.read_text(encoding='utf-8')
        for label,pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                if label=='device address' and match.group(0).upper()=='AA:BB:CC:DD:EE:FF': continue
                errors.append(name+': '+label)
        for term in terms:
            if re.search(r'(?<![A-Za-z0-9])'+re.escape(term)+r'(?![A-Za-z0-9])',name+'\n'+content,re.I):
                errors.append(name+': excluded term')
        if path.suffix=='.md':
            links=re.findall(r'!?\[[^\]]*\]\(([^)]+)\)|src="([^"]+)"',content)
            for pair in links:
                target=(pair[0] or pair[1]).split('#')[0]
                if not target or '://' in target or target.startswith('mailto:'): continue
                resolved=(path.parent/target).resolve()
                if not resolved.is_relative_to(ROOT) or resolved.relative_to(ROOT).as_posix() not in included:
                    errors.append(name+': missing public link '+target)
    if errors: raise ValueError('\n'.join(sorted(set(errors))))

def release(files):
    target=ROOT/'dist'; target.mkdir(exist_ok=True)
    version=re.search(r'^version\s*=\s*"([^"]+)"', (ROOT/'pyproject.toml').read_text(encoding='utf-8'),re.M).group(1)
    archive=target/f'minitoo-pixeldeck-{version}.zip'
    hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for path,name in files}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path,name in files: bundle.write(path,'minitoo-pixeldeck/'+name)
        bundle.writestr('minitoo-pixeldeck/SHA256SUMS.txt',''.join(f'{value}  {name}\n' for name,value in hashes.items()))
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip(): raise ValueError('ZIP CRC failed')
        for name,digest in hashes.items():
            if hashlib.sha256(bundle.read('minitoo-pixeldeck/'+name)).hexdigest()!=digest:
                raise ValueError('Archive checksum mismatch')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
    return {'archive':str(archive.relative_to(ROOT)),'bytes':archive.stat().st_size,'sha256':digest}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--deny-term',action='append',default=[])
    args=parser.parse_args(); files=list(selected_files()); audit(files,args.deny_term)
    result={'public_files':len(files),'content_audit':'passed','local_links':'passed'}
    if not args.check: result.update(release(files))
    print(json.dumps(result,indent=2))
