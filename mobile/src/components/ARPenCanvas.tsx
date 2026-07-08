import React, { useRef, useEffect } from 'react';
import { View, Platform } from 'react-native';
import { WebView } from 'react-native-webview';

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
  </script>
</body>
</html>
`;

export function ARPenCanvas({ color = '#00E5FF', lineWidth = 3, visible = true }: ARPenCanvasProps) {
  const webViewRef = useRef<any>(null);
  const injectedJS = `
    (function() {
      window.setStyle('${color}', ${lineWidth});
    })();
    true;
  `;

  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        webViewRef.current?.injectJavaScript(injectedJS);
      } catch {}
    }, 100);
    return () => clearTimeout(timer);
  }, [color, lineWidth]);

  if (!visible) return null;

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, pointerEvents: 'auto' }}>
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
