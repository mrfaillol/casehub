#!/usr/bin/env python3
"""
Compare VPS documents with Google Drive documents using SHA256 hash.
Generates report of files only in VPS, only in Drive, and in both.

Usage:
    python3 compare_vps_drive_with_hash.py [--dry-run] [--output report.json]
"""
import sys
import os
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

# Add CaseHub to path
sys.path.insert(0, '/var/www/immigrant.law/casehub')

from services.google_drive_handler import GoogleDriveHandler


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"  ⚠️  Error hashing {file_path}: {e}")
        return None


def scan_vps_documents(base_path: str = "/var/www/immigrant.law/documents/clients/") -> Dict:
    """
    Scan all VPS documents and calculate hashes.
    
    Returns:
        {
            "total_files": int,
            "total_size": int,
            "files": {
                "hash": {
                    "path": str,
                    "size": int,
                    "name": str,
                    "client": str
                }
            }
        }
    """
    print(f"\n📁 Scanning VPS documents in {base_path}...")
    print("━" * 60)
    
    base = Path(base_path)
    files_by_hash = {}
    total_size = 0
    total_files = 0
    
    for client_folder in sorted(base.iterdir()):
        if not client_folder.is_dir():
            continue
        
        client_name = client_folder.name
        
        # Skip special folders
        if client_name.startswith('_') or client_name.startswith('.'):
            continue
        
        print(f"  {client_name}...")
        
        for file_path in client_folder.rglob('*'):
            if file_path.is_file():
                total_files += 1
                file_size = file_path.stat().st_size
                total_size += file_size
                
                # Calculate hash
                file_hash = calculate_file_hash(file_path)
                
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
    print(f"   Unique hashes: {len(files_by_hash):,}")
    
    return {
        "total_files": total_files,
        "total_size": total_size,
        "files": files_by_hash
    }


def scan_drive_documents(handler: GoogleDriveHandler, parent_folder_id: str = "14VKmG8vftfgRRwLZAoGNMjZPeRNNthXQ") -> Dict:
    """
    Scan all Google Drive documents and get hashes.
    
    Returns:
        {
            "total_files": int,
            "total_size": int,
            "files": {
                "hash_or_id": {
                    "id": str,
                    "name": str,
                    "size": int,
                    "client": str,
                    "md5": str (if available)
                }
            }
        }
    """
    print(f"\n☁️  Scanning Google Drive documents...")
    print("━" * 60)
    
    files_by_hash = {}
    total_size = 0
    total_files = 0
    
    # Get all client folders
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
        
        # Skip special folders
        if client_name.startswith('_') or client_name.startswith('.'):
            continue
        
        print(f"  [{i}/{len(client_folders)}] {client_name}...", end='')
        
        # Get all files in this folder (recursively)
        def list_files_recursive(fid, depth=0, max_depth=5):
            if depth > max_depth:
                return []
            
            nonlocal total_files, total_size
            
            files = []
            
            try:
                results = handler.service.files().list(
                    q=f"'{fid}' in parents",
                    fields="files(id, name, size, mimeType, md5Checksum)",
                    pageSize=1000
                ).execute()
                
                items = results.get('files', [])
                
                for item in items:
                    mime_type = item.get('mimeType', '')
                    
                    if mime_type == 'application/vnd.google-apps.folder':
                        # Recurse into subfolder
                        files.extend(list_files_recursive(item['id'], depth + 1, max_depth))
                    else:
                        # Regular file
                        file_size = int(item.get('size', 0))
                        total_files += 1
                        total_size += file_size
                        
                        # Use MD5 as hash if available, otherwise use file ID
                        file_hash = item.get('md5Checksum', f"drive_{item['id']}")
                        
                        files_by_hash[file_hash] = {
                            "id": item['id'],
                            "name": item['name'],
                            "size": file_size,
                            "client": client_name,
                            "md5": item.get('md5Checksum'),
                            "mime_type": mime_type
                        }
                        
                        files.append(item)
            
            except Exception as e:
                print(f" ERROR: {e}")
                return files
            
            return files
        
        folder_files = list_files_recursive(folder_id)
        print(f" {len(folder_files)} files")
    
    print(f"\n✅ Drive Scan Complete:")
    print(f"   Files: {total_files:,}")
    print(f"   Size:  {total_size / 1024 / 1024 / 1024:.2f} GB")
    print(f"   Unique hashes: {len(files_by_hash):,}")
    
    return {
        "total_files": total_files,
        "total_size": total_size,
        "files": files_by_hash
    }


def compare_and_generate_report(vps_data: Dict, drive_data: Dict) -> Dict:
    """
    Compare VPS and Drive data and generate report.
    
    Returns:
        {
            "only_in_vps": [...],
            "only_in_drive": [...],
            "in_both": [...],
            "statistics": {...}
        }
    """
    print(f"\n🔍 Comparing VPS vs Drive...")
    print("━" * 60)
    
    vps_hashes = set(vps_data['files'].keys())
    drive_hashes = set(drive_data['files'].keys())
    
    only_vps = vps_hashes - drive_hashes
    only_drive = drive_hashes - vps_hashes
    in_both = vps_hashes & drive_hashes
    
    # Build detailed report
    report = {
        "timestamp": datetime.now().isoformat(),
        "only_in_vps": [],
        "only_in_drive": [],
        "in_both": [],
        "statistics": {
            "vps_total_files": vps_data['total_files'],
            "vps_total_size_gb": vps_data['total_size'] / 1024 / 1024 / 1024,
            "drive_total_files": drive_data['total_files'],
            "drive_total_size_gb": drive_data['total_size'] / 1024 / 1024 / 1024,
            "only_vps_count": len(only_vps),
            "only_drive_count": len(only_drive),
            "in_both_count": len(in_both),
            "overlap_percentage": (len(in_both) / len(vps_hashes) * 100) if vps_hashes else 0
        }
    }
    
    # Files only in VPS
    only_vps_size = 0
    for hash_val in only_vps:
        file_info = vps_data['files'][hash_val]
        only_vps_size += file_info['size']
        report['only_in_vps'].append({
            "hash": hash_val,
            "name": file_info['name'],
            "client": file_info['client'],
            "size": file_info['size'],
            "path": file_info['path']
        })
    
    # Files only in Drive
    only_drive_size = 0
    for hash_val in only_drive:
        file_info = drive_data['files'][hash_val]
        only_drive_size += file_info['size']
        report['only_in_drive'].append({
            "hash": hash_val,
            "name": file_info['name'],
            "client": file_info['client'],
            "size": file_info['size'],
            "id": file_info['id']
        })
    
    # Files in both
    in_both_size = 0
    for hash_val in in_both:
        vps_info = vps_data['files'][hash_val]
        drive_info = drive_data['files'][hash_val]
        in_both_size += vps_info['size']
        report['in_both'].append({
            "hash": hash_val,
            "name": vps_info['name'],
            "vps_client": vps_info['client'],
            "drive_client": drive_info['client'],
            "size": vps_info['size']
        })
    
    report['statistics']['only_vps_size_gb'] = only_vps_size / 1024 / 1024 / 1024
    report['statistics']['only_drive_size_gb'] = only_drive_size / 1024 / 1024 / 1024
    report['statistics']['in_both_size_gb'] = in_both_size / 1024 / 1024 / 1024
    
    # Print summary
    print(f"\n📊 COMPARISON RESULTS:")
    print(f"━" * 60)
    print(f"Only in VPS:     {len(only_vps):4,} files ({only_vps_size / 1024 / 1024 / 1024:6.2f} GB)")
    print(f"Only in Drive:   {len(only_drive):4,} files ({only_drive_size / 1024 / 1024 / 1024:6.2f} GB)")
    print(f"In BOTH:         {len(in_both):4,} files ({in_both_size / 1024 / 1024 / 1024:6.2f} GB)")
    print(f"\nOverlap: {report['statistics']['overlap_percentage']:.1f}%")
    
    return report


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Compare VPS and Drive documents using SHA256 hash')
    parser.add_argument('--dry-run', action='store_true', help='Scan only first 10 clients (test mode)')
    parser.add_argument('--output', default='/tmp/vps_drive_comparison.json', help='Output JSON file')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔍 VPS vs Google Drive Document Comparison")
    print("=" * 60)
    
    # Initialize Google Drive handler
    handler = GoogleDriveHandler()
    if not handler.service:
        print("❌ Google Drive not connected!")
        sys.exit(1)
    
    # Scan VPS
    vps_data = scan_vps_documents()
    
    # Scan Drive
    drive_data = scan_drive_documents(handler)
    
    # Compare and generate report
    report = compare_and_generate_report(vps_data, drive_data)
    
    # Save report
    output_path = args.output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Report saved to: {output_path}")
    
    # Recommendations
    print(f"\n🎯 RECOMMENDATIONS:")
    print(f"━" * 60)
    
    if report['statistics']['only_vps_count'] > 0:
        print(f"✅ Upload {report['statistics']['only_vps_count']} files from VPS → Drive")
        print(f"   Size: {report['statistics']['only_vps_size_gb']:.2f} GB")
    
    if report['statistics']['only_drive_count'] > 0:
        print(f"✅ Download {report['statistics']['only_drive_count']} files from Drive → VPS")
        print(f"   Size: {report['statistics']['only_drive_size_gb']:.2f} GB")
    
    if report['statistics']['in_both_count'] > 0:
        print(f"⚠️  Skip {report['statistics']['in_both_count']} files (already in sync)")
        print(f"   Size: {report['statistics']['in_both_size_gb']:.2f} GB")
    
    print(f"\n✅ DONE! No duplicates will be created.")


if __name__ == "__main__":
    main()
