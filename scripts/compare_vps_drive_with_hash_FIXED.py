#!/usr/bin/env python3
"""
Compare VPS documents with Google Drive documents using MD5 hash (compatible with Drive API).
Fixed version: Uses MD5 for both VPS and Drive to enable proper comparison.
"""
import sys
import os
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict

sys.path.insert(0, '/var/www/immigrant.law/casehub')
from services.google_drive_handler import GoogleDriveHandler


def calculate_md5_hash(file_path: Path) -> str:
    """Calculate MD5 hash of a file (compatible with Google Drive)."""
    md5 = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception as e:
        print(f"  ⚠️  Error hashing {file_path}: {e}")
        return None


def scan_vps_documents(base_path: str = "/var/www/immigrant.law/documents/clients/") -> Dict:
    """Scan VPS documents and calculate MD5 hashes."""
    print(f"\n📁 Scanning VPS documents (calculating MD5)...")
    print("━" * 60)
    
    base = Path(base_path)
    files_by_hash = {}
    total_size = 0
    total_files = 0
    
    for client_folder in sorted(base.iterdir()):
        if not client_folder.is_dir() or client_folder.name.startswith(('_', '.')):
            continue
        
        client_name = client_folder.name
        print(f"  {client_name}...")
        
        for file_path in client_folder.rglob('*'):
            if file_path.is_file():
                total_files += 1
                file_size = file_path.stat().st_size
                total_size += file_size
                
                # Calculate MD5 (same as Drive uses)
                file_hash = calculate_md5_hash(file_path)
                
                if file_hash:
                    files_by_hash[file_hash] = {
                        "path": str(file_path),
                        "size": file_size,
                        "name": file_path.name,
                        "client": client_name,
                        "relative_path": str(file_path.relative_to(base))
                    }
    
    print(f"\n✅ VPS Scan Complete:")
    print(f"   Files: {total_files:,}")
    print(f"   Size:  {total_size / 1024 / 1024 / 1024:.2f} GB")
    print(f"   Unique MD5 hashes: {len(files_by_hash):,}")
    
    return {"total_files": total_files, "total_size": total_size, "files": files_by_hash}


def scan_drive_documents(handler, parent_folder_id="14VKmG8vftfgRRwLZAoGNMjZPeRNNthXQ") -> Dict:
    """Scan Google Drive documents and get MD5 checksums."""
    print(f"\n☁️  Scanning Google Drive documents (using MD5)...")
    print("━" * 60)
    
    files_by_hash = {}
    total_size = 0
    total_files = 0
    
    results = handler.service.files().list(
        q=f"'{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)",
        pageSize=1000
    ).execute()
    
    client_folders = results.get('files', [])
    print(f"Found {len(client_folders)} client folders\n")
    
    for i, folder in enumerate(client_folders, 1):
        client_name = folder['name']
        folder_id = folder['id']
        
        if client_name.startswith(('_', '.')):
            continue
        
        print(f"  [{i}/{len(client_folders)}] {client_name}...", end='')
        
        def list_files_recursive(fid, depth=0):
            if depth > 5:
                return []
            
            nonlocal total_files, total_size, files_by_hash
            
            try:
                results = handler.service.files().list(
                    q=f"'{fid}' in parents",
                    fields="files(id, name, size, mimeType, md5Checksum)",
                    pageSize=1000
                ).execute()
                
                items = results.get('files', [])
                file_count = 0
                
                for item in items:
                    mime_type = item.get('mimeType', '')
                    
                    if mime_type == 'application/vnd.google-apps.folder':
                        list_files_recursive(item['id'], depth + 1)
                    else:
                        md5 = item.get('md5Checksum')
                        if md5:  # Only process files with MD5
                            file_size = int(item.get('size', 0))
                            total_files += 1
                            total_size += file_size
                            file_count += 1
                            
                            files_by_hash[md5] = {
                                "id": item['id'],
                                "name": item['name'],
                                "size": file_size,
                                "client": client_name,
                                "md5": md5,
                                "mime_type": mime_type
                            }
                
                return file_count
            except Exception as e:
                print(f" ERROR: {e}")
                return 0
        
        count = list_files_recursive(folder_id)
        print(f" {count} files")
    
    print(f"\n✅ Drive Scan Complete:")
    print(f"   Files: {total_files:,}")
    print(f"   Size:  {total_size / 1024 / 1024 / 1024:.2f} GB")
    print(f"   Unique MD5 hashes: {len(files_by_hash):,}")
    
    return {"total_files": total_files, "total_size": total_size, "files": files_by_hash}


def compare_and_generate_report(vps_data: Dict, drive_data: Dict) -> Dict:
    """Compare using MD5 hashes."""
    print(f"\n🔍 Comparing VPS vs Drive (MD5 hashes)...")
    print("━" * 60)
    
    vps_hashes = set(vps_data['files'].keys())
    drive_hashes = set(drive_data['files'].keys())
    
    only_vps = vps_hashes - drive_hashes
    only_drive = drive_hashes - vps_hashes
    in_both = vps_hashes & drive_hashes
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "only_in_vps": [],
        "only_in_drive": [],
        "in_both": [],
        "statistics": {
            "vps_total_files": vps_data['total_files'],
            "drive_total_files": drive_data['total_files'],
            "only_vps_count": len(only_vps),
            "only_drive_count": len(only_drive),
            "in_both_count": len(in_both),
            "overlap_percentage": (len(in_both) / len(vps_hashes) * 100) if vps_hashes else 0
        }
    }
    
    # Build detailed lists
    only_vps_size = 0
    for md5 in only_vps:
        file_info = vps_data['files'][md5]
        only_vps_size += file_info['size']
        report['only_in_vps'].append({
            "md5": md5,
            "name": file_info['name'],
            "client": file_info['client'],
            "size": file_info['size'],
            "path": file_info['path']
        })
    
    only_drive_size = 0
    for md5 in only_drive:
        file_info = drive_data['files'][md5]
        only_drive_size += file_info['size']
        report['only_in_drive'].append({
            "md5": md5,
            "name": file_info['name'],
            "client": file_info['client'],
            "size": file_info['size'],
            "id": file_info['id']
        })
    
    in_both_size = 0
    for md5 in in_both:
        vps_info = vps_data['files'][md5]
        drive_info = drive_data['files'][md5]
        in_both_size += vps_info['size']
        report['in_both'].append({
            "md5": md5,
            "name": vps_info['name'],
            "vps_client": vps_info['client'],
            "drive_client": drive_info['client'],
            "size": vps_info['size']
        })
    
    report['statistics']['only_vps_size_gb'] = only_vps_size / 1024 / 1024 / 1024
    report['statistics']['only_drive_size_gb'] = only_drive_size / 1024 / 1024 / 1024
    report['statistics']['in_both_size_gb'] = in_both_size / 1024 / 1024 / 1024
    
    print(f"\n📊 RESULTS:")
    print(f"━" * 60)
    print(f"Only in VPS:     {len(only_vps):4,} files ({only_vps_size / 1024 / 1024 / 1024:6.2f} GB)")
    print(f"Only in Drive:   {len(only_drive):4,} files ({only_drive_size / 1024 / 1024 / 1024:6.2f} GB)")
    print(f"In BOTH:         {len(in_both):4,} files ({in_both_size / 1024 / 1024 / 1024:6.2f} GB)")
    print(f"\nOverlap: {report['statistics']['overlap_percentage']:.1f}%")
    
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='/tmp/vps_drive_comparison_md5.json')
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔍 VPS vs Drive Comparison (MD5 - FIXED)")
    print("=" * 60)
    
    handler = GoogleDriveHandler()
    if not handler.service:
        print("❌ Drive not connected!")
        sys.exit(1)
    
    vps_data = scan_vps_documents()
    drive_data = scan_drive_documents(handler)
    report = compare_and_generate_report(vps_data, drive_data)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Report: {args.output}")
    
    if report['statistics']['only_vps_count'] > 0:
        print(f"\n✅ Upload {report['statistics']['only_vps_count']} files VPS → Drive ({report['statistics']['only_vps_size_gb']:.2f} GB)")
    if report['statistics']['only_drive_count'] > 0:
        print(f"✅ Download {report['statistics']['only_drive_count']} files Drive → VPS ({report['statistics']['only_drive_size_gb']:.2f} GB)")
    if report['statistics']['in_both_count'] > 0:
        print(f"⚠️  Skip {report['statistics']['in_both_count']} duplicates ({report['statistics']['in_both_size_gb']:.2f} GB)")


if __name__ == "__main__":
    main()
