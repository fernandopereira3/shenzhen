// Inclina os cards conforme o mouse. O ângulo segue o cursor com atraso
// (lerp a cada frame), o que dá o efeito de profundidade "pesada".
(() => {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const MAX = 14;      // inclinação máxima em graus
  const SUAVE = 0.12;  // fração do caminho percorrida por frame

  document.querySelectorAll('.bot-card').forEach((card) => {
    const alvo = { x: 0, y: 0 };
    const atual = { x: 0, y: 0 };
    let animando = false;

    const passo = () => {
      atual.x += (alvo.x - atual.x) * SUAVE;
      atual.y += (alvo.y - atual.y) * SUAVE;
      card.style.setProperty('--rx', `${atual.x.toFixed(2)}deg`);
      card.style.setProperty('--ry', `${atual.y.toFixed(2)}deg`);
      const parado = Math.abs(alvo.x - atual.x) < 0.01 && Math.abs(alvo.y - atual.y) < 0.01;
      animando = !parado;
      if (animando) requestAnimationFrame(passo);
    };
    const animar = () => {
      if (!animando) { animando = true; requestAnimationFrame(passo); }
    };

    card.addEventListener('pointermove', (e) => {
      const r = card.getBoundingClientRect();
      const nx = (e.clientX - r.left) / r.width - 0.5;  // -0.5 .. 0.5
      const ny = (e.clientY - r.top) / r.height - 0.5;
      alvo.x = -ny * 2 * MAX;
      alvo.y = nx * 2 * MAX;
      animar();
    });
    card.addEventListener('pointerleave', () => {
      alvo.x = 0;
      alvo.y = 0;
      animar();
    });
  });
})();
