import * as ex from 'excalibur';
import { attachNanoCalibur } from './nanocalibur_generated';

const game = new ex.Engine({
  width: 800,
  height: 600,
  canvasElementId: 'game'
});

const scene = new ex.Scene();
game.add('main', scene);
game.goToScene('main');

const bridge = attachNanoCalibur(scene);
game.on('postupdate', () => {
  bridge.tick();
});

game.start();