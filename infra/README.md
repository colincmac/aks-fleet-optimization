# Infrastructure Templates

Infrastructure deployment is not required for local assessments. Start with the
[guided tutorial](../docs/accelerator-docs/getting-started.md) and
[assessment guide](../docs/accelerator-docs/assessment-guide.md).

The [Bicep template](main.bicep) creates a user-assigned managed identity and a
storage account with public network access, shared-key access and anonymous blob
access disabled. Deploying it creates Azure resources and may incur charges.

It does not deploy the advisor, create a report container, configure private
connectivity, schedule collection or assign roles. The `containerImage` parameter
is returned as an output; no image is executed. Do not treat this template as a
complete hosted solution or deploy it merely to run the CLI.

The advisor identity must remain read-only. Do not grant Contributor or
Kubernetes write permissions to make an assessment run.
