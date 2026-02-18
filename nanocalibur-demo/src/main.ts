import {
  attachNanoCalibur,
  type CanvasHostOptions,
} from './nanocalibur_generated';

function requireCanvas(canvasId: string): HTMLCanvasElement {
  const element = document.getElementById(canvasId);
  if (!(element instanceof HTMLCanvasElement)) {
    throw new Error(`Canvas element '#${canvasId}' was not found.`);
  }
  return element;
}

function requireSymbolicPanel(panelId: string): HTMLElement {
  const element = document.getElementById(panelId);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Symbolic panel '#${panelId}' was not found.`);
  }
  return element;
}

function formatSymbolicFrame(host: ReturnType<typeof attachNanoCalibur>): string {
  const frame = host.getSymbolicFrame();
  const legend = frame.legend
    .map((item) => `${item.symbol}: ${item.description}`)
    .join('\n');
  if (!legend) {
    return frame.rows.join('\n');
  }
  return `${frame.rows.join('\n')}\n\nLegend\n${legend}`;
}

const canvas = requireCanvas('game');
const symbolicPanel = requireSymbolicPanel('symbolic');

const hostOptions: CanvasHostOptions = {
  width: 960,
  height: 640,
  backgroundColor: '#121826',
  tileColor: '#303a52',
  pixelated: true,
  showHud: true,
};

const host = attachNanoCalibur(canvas, hostOptions);
const renderSymbolic = (): void => {
  symbolicPanel.textContent = formatSymbolicFrame(host);
  window.requestAnimationFrame(renderSymbolic);
};

void host.start().then(() => {
  renderSymbolic();
}).catch((error: unknown) => {
  console.error('Failed to start NanoCalibur CanvasHost.', error);
});
