"""
Author: M. Dijkens
Date last modified: 2026-10-22
License: MIT
Description: Offline configuration and named-environment check, without printing values.
"""
import argparse
import importlib.metadata
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Check setup readiness; --fusion also requires the weekly password."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fusion', action='store_true', help='Require the Fusion password too.')
    args = parser.parse_args()
    failed = False

    def report(name: str, ok: bool, note: str = '') -> None:
        nonlocal failed
        print(f'{"OK" if ok else "MISSING/INVALID"}: {name}' + (f' ({note})' if note else ''))
        failed |= not ok

    report('Python', sys.version_info[:2] == (3, 11), f'{sys.version_info.major}.{sys.version_info.minor}')
    report('Named Conda environment fusionmcp', Path(sys.prefix).name.lower() == 'fusionmcp')
    report('Private .env exists', (ROOT / '.env').is_file())
    try:
        values = {**dotenv_values(ROOT / '.env', interpolate=False), **os.environ}
    except Exception:
        print('INVALID: .env could not be read; contents hidden.')
        return 1
    required = [
        'GENAI_REGION', 'GENAI_PROJECT_ID', 'GENAI_MODEL', 'GENAI_API_KEY',
        'FUSION_BASE_URL', 'FUSION_USERNAME', 'FUSION_WORKFLOW',
        'OCI_REGION', 'OCI_CLI_PROFILE', 'OCI_COMPARTMENT_NAME', 'OCI_COMPARTMENT_ID',
        'OCIR_TENANCY_NAMESPACE', 'OCIR_USERNAME', 'OCIR_REPOSITORY',
        'OCI_HOSTED_APPLICATION_NAME', 'OCI_HOSTED_DEPLOYMENT_NAME',
    ]
    if args.fusion:
        required.append('FUSION_PASSWORD')
    for name in required:
        value = values.get(name)
        report(name, bool(value and str(value).strip() and not str(value).startswith('replace-with-')))
    report('GENAI_AUTH_MODE', values.get('GENAI_AUTH_MODE') == 'api_key')
    report('Fusion HTTPS origin', bool(
        (url := urlparse(str(values.get('FUSION_BASE_URL') or ''))).scheme == 'https'
        and url.hostname and not url.username and not url.password
        and url.path in ('', '/') and not url.query and not url.fragment
    ))
    for filename in ('.gitignore', '.dockerignore'):
        lines = (ROOT / filename).read_text(encoding='utf-8').splitlines()
        report(f'{filename} excludes .env', '.env' in lines and '.env.*' in lines)
    for package in ('fastmcp', 'httpx', 'openai', 'python-dotenv', 'uvicorn'):
        try:
            version = importlib.metadata.version(package)
            report(f'Package {package}', True, version)
        except importlib.metadata.PackageNotFoundError:
            report(f'Package {package}', False)
    if not args.fusion and not values.get('FUSION_PASSWORD'):
        print('OPTIONAL: FUSION_PASSWORD is empty; supply before step 2 or through the later UI.')
    print('No Fusion, EAI or OCI calls were made. Secret values are not displayed.')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
