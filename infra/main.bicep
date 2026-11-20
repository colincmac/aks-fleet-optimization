targetScope = 'resourceGroup'

@description('Azure region for deployment resources.')
param location string = resourceGroup().location

@description('Globally unique lowercase storage account name.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Container image digest or immutable tag. Never use latest in production.')
param containerImage string

@description('Deployment name prefix.')
param namePrefix string = 'aks-efficiency'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id'
  location: location
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Disabled'
  }
}

// TODO(AKS-PLATFORM-001): Add private networking, report container, Container Apps environment,
// scheduled job, diagnostics, and narrowly scoped role assignments. Keep collection read-only.

output managedIdentityResourceId string = identity.id
output storageAccountResourceId string = storage.id
output configuredImage string = containerImage
