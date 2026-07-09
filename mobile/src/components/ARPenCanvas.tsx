import React, { useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { View, Platform } from 'react-native';
import { WebView } from 'react-native-webview';

export interface ARPenCanvasHandle {
  drawText: (text: string, x: number, y: number, color?: string, fontSize?: number) => void;
  drawLine: (x1: number, y1: number, x2: number, y2: number, color?: string) => void;
  drawArrow: (x1: number, y1: number, x2: number, y2: number, color?: string) => void;
  drawStepBox: (stepNum: number, instruction: string, explanation: string, x: number, y: number, color?: string) => void;
  clearAll: () => void;
  getDataUrl: () => Promise<string | null>;
}

interface ARPenCanvasProps {
  color?: string;
  lineWidth?: number;
  visible?: boolean;
}

const CANVAS_HTML = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; touch-action: none; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: transparent; }
    canvas { display: block; background: transparent; }
  </style>
</head>
<body>
  <canvas id="canvas"></canvas>
  <script>
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    let drawing = false;
    let lastX = 0;
    let lastY = 0;
    let currentColor = '#00E5FF';
    let currentWidth = 3;

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

    function getPos(e) {
      const rect = canvas.getBoundingClientRect();
      if (e.touches && e.touches.length > 0) {
        return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top };
      }
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    function start(e) {
      e.preventDefault();
      drawing = true;
      const pos = getPos(e);
      lastX = pos.x;
      lastY = pos.y;
      ctx.beginPath();
      ctx.moveTo(lastX, lastY);
    }

    function move(e) {
      e.preventDefault();
      if (!drawing) return;
      const pos = getPos(e);
      ctx.strokeStyle = currentColor;
      ctx.lineWidth = currentWidth;
      ctx.beginPath();
      ctx.moveTo(lastX, lastY);
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
      lastX = pos.x;
      lastY = pos.y;
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

    window.setStyle = function(color, width) {
      currentColor = color || currentColor;
      currentWidth = width || currentWidth;
    };

    window.clearCanvas = function() {
      const dpr = window.devicePixelRatio || 1;
      ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    };

    window.drawText = function(text, x, y, color, fontSize) {
      if (!text) return;
      ctx.fillStyle = color || currentColor;
      ctx.font = (fontSize || 16) + 'px sans-serif';
      ctx.textBaseline = 'top';
      const lines = text.split('\\n');
      lines.forEach((line, i) => {
        ctx.fillText(line, x, y + i * (fontSize || 16) * 1.3);
      });
    };

    window.drawLine = function(x1, y1, x2, y2, color, width) {
      ctx.strokeStyle = color || currentColor;
      ctx.lineWidth = width || currentWidth;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    };

    window.drawArrow = function(x1, y1, x2, y2, color) {
      const headLen = 10;
      const angle = Math.atan2(y2 - y1, x2 - x1);
      ctx.strokeStyle = color || currentColor;
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
      ctx.fillStyle = color || currentColor;
      ctx.fill();
    };

    window.drawRoundedBox = function(x, y, w, h, color, bgColor) {
      const r = 8;
      ctx.fillStyle = bgColor || 'rgba(0, 212, 255, 0.12)';
      ctx.strokeStyle = color || currentColor;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + w - r, y);
      ctx.quadraticCurveTo(x + w, y, x + w, y + r);
      ctx.lineTo(x + w, y + h - r);
      ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      ctx.lineTo(x + r, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - r);
      ctx.lineTo(x, y + r);
      ctx.quadraticCurveTo(x, y, x + r, y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    };

    window.getCanvasDataUrl = function() {
      return canvas.toDataURL('image/png');
    };
  </script>
</body>
</html>
`;

export const ARPenCanvas = forwardRef<ARPenCanvasHandle, ARPenCanvasProps>(
  ({ color = '#00E5FF', lineWidth = 3, visible = true }, ref) => {
    const webViewRef = useRef<any>(null);
    const readyRef = useRef(false);

    const inject = (js: string) => {
      try {
        webViewRef.current?.injectJavaScript(js);
      } catch {}
    };

    useImperativeHandle(ref, () => ({
      drawText(text, x, y, c, fontSize) {
        const escaped = text.replace(/'/g, "\\'").replace(/\n/g, '\\n');
        inject(`window.drawText('${escaped}', ${x}, ${y}, '${c || color}', ${fontSize || 16}); true;`);
      },
      drawLine(x1, y1, x2, y2, c) {
        inject(`window.drawLine(${x1}, ${y1}, ${x2}, ${y2}, '${c || color}', ${lineWidth}); true;`);
      },
      drawArrow(x1, y1, x2, y2, c) {
        inject(`window.drawArrow(${x1}, ${y1}, ${x2}, ${y2}, '${c || color}'); true;`);
      },
      drawStepBox(stepNum, instruction, explanation, x, y, c) {
        const clr = c || color;
        const icon = `Step ${stepNum}`;
        inject(`
          window.drawRoundedBox(${x}, ${y}, 280, 70, '${clr}', '${clr}18');
          window.drawText('${icon}', ${x + 10}, ${y + 8}, '${clr}', 11);
          window.drawText('${instruction.replace(/'/g, "\\'")}', ${x + 10}, ${y + 26}, '#ffffff', 14);
          true;
        `);
      },
      clearAll() {
        inject('window.clearCanvas(); true;');
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
    }), [color, lineWidth]);

    useEffect(() => {
      const timer = setTimeout(() => {
        inject(`window.setStyle('${color}', ${lineWidth}); true;`);
        readyRef.current = true;
      }, 200);
      return () => clearTimeout(timer);
    }, [color, lineWidth]);

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
