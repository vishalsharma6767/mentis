import React, { useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { View, Platform } from 'react-native';
import { WebView } from 'react-native-webview';

export interface ARPenCanvasHandle {
  movePen: (x: number, y: number) => void;
  write: (text: string, color?: string) => void;
  writeln: (text: string, color?: string) => void;
  clearAll: () => void;
  getDataUrl: () => Promise<string | null>;
  drawUnderline: (y: number, width: number, color?: string) => void;
  drawCircle: (x: number, y: number, radius: number, color?: string) => void;
  drawArrow: (x1: number, y1: number, x2: number, y2: number, color?: string) => void;
  setPenColor: (color: string) => void;
}

const CANVAS_HTML = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: transparent; }
    canvas { display: block; }
  </style>
</head>
<body>
  <canvas id="canvas"></canvas>
  <script>
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    let penX = 40;
    let penY = 40;
    let penColor = '#00E5FF';
    let penSize = 3;
    let penVisible = false;
    let lineHeight = 42;
    let charWidth = 14;
    let drawing = false;
    let lastX = 0;
    let lastY = 0;

    function resize() {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.style.width = window.innerWidth + 'px';
      canvas.style.height = window.innerHeight + 'px';
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
    }
    window.addEventListener('resize', resize);
    resize();

    function drawPenCursor() {
      if (!penVisible) return;
      ctx.beginPath();
      ctx.arc(penX, penY, penSize + 2, 0, Math.PI * 2);
      ctx.fillStyle = penColor;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(penX, penY, penSize + 5, 0, Math.PI * 2);
      ctx.strokeStyle = penColor + '60';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    function redraw() {}

    function escapeText(t) {
      return t.replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'").replace(/\\n/g, '\\\\n');
    }

    window.setPenColor = function(color) {
      penColor = color || penColor;
    };

    window.setPenVisible = function(visible) {
      penVisible = visible;
      if (visible) { redraw(); drawPenCursor(); }
    };

    window.movePenTo = function(x, y) {
      penX = x;
      penY = y;
      if (penVisible) { redraw(); drawPenCursor(); }
    };

    window.clearAll = function() {
      const dpr = window.devicePixelRatio || 1;
      ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
      penX = 40;
      penY = 40;
    };

    function drawChar(c, x, y, color, size) {
      ctx.fillStyle = color || penColor;
      ctx.font = (size || 24) + 'px "Times New Roman", serif';
      ctx.textBaseline = 'top';
      var w = ctx.measureText(c).width || charWidth;
      ctx.fillText(c, x, y);
      return w;
    }

    function sleep(ms) {
      return new Promise(function(r) { setTimeout(r, ms); });
    }

    window.writeText = async function(text, color, isNewLine) {
      var c = color || penColor;
      var startX = penX;
      var startY = penY;
      if (isNewLine && text) {
        startX = 40;
        startY = penY + lineHeight;
        penX = 40;
        penY = startY;
      }
      penVisible = true;
      drawPenCursor();
      for (var i = 0; i < text.length; i++) {
        var ch = text[i];
        if (ch === ' ') {
          penX += charWidth * 0.6;
          continue;
        }
        var wobbleX = (Math.random() - 0.5) * 1.2;
        var wobbleY = (Math.random() - 0.5) * 1.2;
        var w = drawChar(ch, penX + wobbleX, penY + wobbleY, c, 24);
        penX += w + 1;
        var dpr = window.devicePixelRatio || 1;
        ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
        ctx.putImageData(ctx.getImageData(0, 0, canvas.width / dpr, canvas.height / dpr), 0, 0);
        ctx.beginPath();
        ctx.arc(penX, penY, penSize + 2, 0, Math.PI * 2);
        ctx.fillStyle = c;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(penX, penY, penSize + 5, 0, Math.PI * 2);
        ctx.strokeStyle = c + '60';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        await sleep(30);
      }
      penVisible = false;
    };

    window.drawSimpleLine = function(x1, y1, x2, y2, color) {
      ctx.strokeStyle = color || penColor;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    };

    window.drawUnderlineFn = function(y, width, color) {
      var c = color || penColor;
      ctx.strokeStyle = c;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(penX, y + 30);
      ctx.lineTo(penX + width, y + 30);
      ctx.stroke();
      penVisible = true;
      penX = penX + width;
      penY = y + 28;
      drawPenCursor();
      setTimeout(function() { penVisible = false; }, 200);
    };

    window.drawCircleFn = function(x, y, radius, color) {
      var c = color || penColor;
      ctx.strokeStyle = c;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.stroke();
    };

    window.drawArrowFn = function(x1, y1, x2, y2, color) {
      var c = color || penColor;
      var headLen = 10;
      var angle = Math.atan2(y2 - y1, x2 - x1);
      ctx.strokeStyle = c;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6));
      ctx.lineTo(x2, y2);
      ctx.fillStyle = c;
      ctx.fill();
    };

    window.getCanvasDataUrl = function() {
      return canvas.toDataURL('image/png');
    };

    function getPos(e) {
      var rect = canvas.getBoundingClientRect();
      if (e.touches && e.touches.length > 0)
        return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top };
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    function start(e) {
      e.preventDefault();
      drawing = true;
      var pos = getPos(e);
      lastX = pos.x; lastY = pos.y;
      ctx.beginPath();
      ctx.moveTo(lastX, lastY);
    }

    function move(e) {
      e.preventDefault();
      if (!drawing) return;
      var pos = getPos(e);
      ctx.strokeStyle = penColor;
      ctx.lineWidth = penSize;
      ctx.beginPath();
      ctx.moveTo(lastX, lastY);
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
      lastX = pos.x; lastY = pos.y;
    }

    function end(e) {
      e.preventDefault();
      drawing = false;
    }

    canvas.addEventListener('mousedown', start);
    canvas.addEventListener('mousemove', move);
    canvas.addEventListener('mouseup', end);
    canvas.addEventListener('mouseleave', end);
    canvas.addEventListener('touchstart', start, { passive: false });
    canvas.addEventListener('touchmove', move, { passive: false });
    canvas.addEventListener('touchend', end);
    canvas.addEventListener('touchcancel', end);

    window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'ready' }));
  </script>
</body>
</html>
`;

export const ARPenCanvas = forwardRef<ARPenCanvasHandle, { color?: string; lineWidth?: number; visible?: boolean }>(
  ({ color = '#00E5FF', lineWidth = 3, visible = true }, ref) => {
    const webViewRef = useRef<any>(null);
    const readyRef = useRef(false);

    const inject = (js: string) => {
      try {
        webViewRef.current?.injectJavaScript(js);
      } catch {}
    };

    useImperativeHandle(ref, () => ({
      movePen(x, y) {
        inject(`window.movePenTo(${x}, ${y}); true;`);
      },
      write(text, c) {
        const escaped = text.replace(/'/g, "\\'").replace(/\n/g, '\\n');
        inject(`window.writeText('${escaped}', '${c || color}', false); true;`);
      },
      writeln(text, c) {
        const escaped = text.replace(/'/g, "\\'").replace(/\n/g, '\\n');
        inject(`window.writeText('${escaped}', '${c || color}', true); true;`);
      },
      clearAll() {
        inject('window.clearAll(); true;');
      },
      getDataUrl(): Promise<string | null> {
        return new Promise((resolve) => {
          const handler = (event: any) => {
            try {
              const data = JSON.parse(event.data);
              if (data.type === 'canvas_data') {
                resolve(data.url);
                window.removeEventListener('message', handler);
              }
            } catch {}
          };
          window.addEventListener('message', handler);
          inject(`
            var url = window.getCanvasDataUrl();
            window.ReactNativeWebView.postMessage(JSON.stringify({type: 'canvas_data', url: url}));
            true;
          `);
          setTimeout(() => {
            window.removeEventListener('message', handler);
            resolve(null);
          }, 3000);
        });
      },
      drawUnderline(y, width, c) {
        inject(`window.drawUnderlineFn(${y}, ${width}, '${c || color}'); true;`);
      },
      drawCircle(x, y, radius, c) {
        inject(`window.drawCircleFn(${x}, ${y}, ${radius}, '${c || color}'); true;`);
      },
      drawArrow(x1, y1, x2, y2, c) {
        inject(`window.drawArrowFn(${x1}, ${y1}, ${x2}, ${y2}, '${c || color}'); true;`);
      },
      setPenColor(c) {
        inject(`window.setPenColor('${c || color}'); true;`);
        penColorRef.current = c || color;
      },
    }), [color, lineWidth]);

    const penColorRef = useRef(color);

    useEffect(() => {
      const timer = setTimeout(() => {
        inject(`window.setPenColor('${color}'); true;`);
        readyRef.current = true;
      }, 200);
      return () => clearTimeout(timer);
    }, [color]);

    if (!visible) return null;

    return (
      <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, pointerEvents: 'auto', zIndex: 50 }}>
        <WebView
          ref={webViewRef}
          source={{ html: CANVAS_HTML }}
          style={{ flex: 1, backgroundColor: 'transparent' }}
          pointerEvents="auto"
          scrollEnabled={false}
          overScrollMode="never"
          javaScriptEnabled={true}
          domStorageEnabled={false}
          startInLoadingState={false}
          originWhitelist={['*']}
          mixedContentMode="always"
          onError={() => {}}
          onHttpError={() => {}}
        />
      </View>
    );
  }
);
