import React from 'react';
import { createRoot } from 'react-dom/client';
import Sidebar from '../../src/components/Sidebar';
import '../../src/index.css';
document.documentElement.dir = new URLSearchParams(location.search).get('dir') || 'ltr';
createRoot(document.getElementById('root')!).render(<main><Sidebar /></main>);
