from __future__ import annotations

import argparse
import sys
from collections.abc import Generator
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import TextIO
from urllib.parse import urlsplit

import yaml

from aks_fleet_efficiency.artifacts import read_model, write_exclusive
from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.collection import CollectionPlan, CollectionReaders, collect_fragments
from aks_fleet_efficiency.collectors.azure_resource_graph import AzureSdkInventoryReader
from aks_fleet_efficiency.collectors.kubernetes_metadata import KubernetesSdkReader
from aks_fleet_efficiency.config import OnboardingConfig, load_onboarding_config
from aks_fleet_efficiency.models import CollectionStatus


@contextmanager
def demo_readers(
    profile: OnboardingConfig,
    plan: CollectionPlan,
    server: str,
    ca_file: Path,
    token: str,
) -> Generator[CollectionReaders]:
    try:
        sdk = import_module("kubernetes.client")
        identity = import_module("azure.identity")
    except ImportError:
        raise RuntimeError("Install the Azure and Kubernetes optional dependencies.") from None
    configuration = sdk.Configuration()
    configuration.host = server
    configuration.ssl_ca_cert = str(ca_file.resolve())
    configuration.verify_ssl = True
    configuration.debug = False
    configuration.retries = 0
    configuration.api_key = {"BearerToken": token}
    configuration.api_key_prefix = {"BearerToken": "Bearer"}
    with (
        sdk.ApiClient(configuration) as client,
        identity.AzureCliCredential(
            tenant_id=str(profile.scope.tenant_id), process_timeout=10
        ) as credential,
        AzureSdkInventoryReader(
            profile, credential=credential, request_timeout_seconds=15
        ) as inventory,
    ):
        target = plan.clusters[0]
        reader = KubernetesSdkReader(
            profile,
            cluster_resource_id=target.resource_id,
            api_client=client,
            request_timeout_seconds=15,
        )
        yield CollectionReaders(inventory=inventory, kubernetes={target.resource_id: reader})


def collect_demo_inventory(
    profile_path: Path,
    plan_path: Path,
    *,
    server: str,
    ca_file: Path,
    token_stream: TextIO,
    output: Path,
    allow_live: bool = False,
) -> int:
    if not allow_live:
        raise PermissionError("Explicit --allow-live is required.")
    profile = load_onboarding_config(profile_path)
    plan = read_model(plan_path, CollectionPlan)
    if (
        len(profile.clusters) != 1
        or len(plan.clusters) != 1
        or profile.clusters[0].resource_id != plan.clusters[0].resource_id
        or profile.metric_sources
        or profile.clusters[0].metric_source is not None
        or profile.analysis.mode != "baseline"
        or not profile.analysis.packs
        or any(
            load_catalog().pack(name).evidence_kind != "inventory"
            for name in profile.analysis.packs
        )
        or plan.workload_assessments
        or plan.clusters[0].entities
        or plan.clusters[0].metadata_export is not None
        or plan.clusters[0].node_history_reference is not None
    ):
        raise ValueError("Use one exact cluster and baseline inventory-only demo inputs.")
    endpoint = urlsplit(server)
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.path not in {"", "/"}
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError("Use the independently verified HTTPS API-server endpoint.")
    if not ca_file.is_file():
        raise ValueError("An approved API-server CA file is required.")
    if output.exists():
        raise FileExistsError("Output must be a new file.")
    if not output.parent.is_dir():
        raise ValueError("Create the protected output parent directory first.")
    token = token_stream.read(16385).strip()
    if not token or len(token) > 16384 or any(character.isspace() for character in token):
        raise ValueError("Provide one bounded short-lived token on standard input.")
    with demo_readers(profile, plan, server, ca_file, token) as readers:
        fragments = collect_fragments(profile, plan, readers, allow_live=True)
    write_exclusive(output, fragments.model_dump_json(indent=2))
    return (
        0
        if all(
            receipt.status == CollectionStatus.COMPLETE
            for receipt in [
                *(item.collection for item in fragments.azure),
                *(item.collection for item in fragments.kubernetes),
            ]
        )
        else 3
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Operator-run current demo inventory; never applies cluster resources."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--ca-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-stdin", action="store_true", required=True)
    parser.add_argument("--allow-live", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        code = collect_demo_inventory(
            arguments.config,
            arguments.plan,
            server=arguments.server,
            ca_file=arguments.ca_file,
            token_stream=sys.stdin,
            output=arguments.output,
            allow_live=arguments.allow_live,
        )
    except PermissionError:
        print(
            "Collection refused: --allow-live and approved read-only access are required.",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, yaml.YAMLError):
        print(
            "Collection rejected: check exact scope, baseline inventory selection, HTTPS/CA, "
            "bounded token input and a new writable output path. Input values are not echoed.",
            file=sys.stderr,
        )
        return 2
    except RuntimeError:
        print(
            "Collection setup failed: install the azure/kubernetes extras and review the runbook.",
            file=sys.stderr,
        )
        return 2
    print(
        "Saved projected inventory fragments; inspect receipts before interpreting findings."
        if code == 0
        else "Saved partial inventory fragments; inspect receipt errors and missing scope."
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
