import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import { App } from './ui/App';
import { SimulatorProvider } from './api/provider';
import { demoRecommendations, demoVpas, packPreviewRecommendation } from './demo/fixtures';

const scenario = new URLSearchParams(location.search).get('scenario');
const records =
  scenario === 'empty' || scenario === 'denied'
    ? []
    : ['baseline', 'guarded', 'unsupported', 'limit', 'floor'].includes(scenario ?? '')
      ? [packPreviewRecommendation(scenario!)]
      : demoRecommendations();
const provider = new SimulatorProvider(records);
if (scenario === 'denied') {
  provider.list = async () => {
    throw new Error('Synthetic permission denied; no API was contacted.');
  };
}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App
        provider={provider}
        basePath="/fleet-efficiency"
        standalone
        vpas={demoVpas(records)}
        onRoleChange={(role) => {
          provider.role = role;
        }}
      />
    </BrowserRouter>
  </React.StrictMode>
);
