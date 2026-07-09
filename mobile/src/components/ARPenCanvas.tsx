import React, { useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { View, Platform } from 'react-native';

const isWeb = Platform.OS === 'web';

export interface ARPenCanvasHandle {
  movePen: (x: number, y: number) => void;
  write: (text: string, color?: string) => void;
  writeln: (text: string, color?: string) => void;
  clearAll: () => void;
  getDataUrl: () => Promise<string | null>;
  drawLine: (x1: number, y1: number, x2: number, y2: number, color?: string) => void;
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
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow-y:auto;background:transparent}
canvas{display:block}
</style>
</head>
<body>
<canvas id="c"></canvas>
<script>
var c=document.getElementById('c'),ctx=c.getContext('2d');
var px=40,py=40,pc='#00E5FF',ps=3,lh=42,cw=14,drawing=false,lx=0,ly=0,baseH=0;

function resize(){
  var d=window.devicePixelRatio||1;
  var w=window.innerWidth;
  var h=Math.max(window.innerHeight,py+100);
  baseH=h;
  c.width=w*d;c.height=h*d;c.style.width=w+'px';c.style.height=h+'px';
  ctx.setTransform(1,0,0,1,0,0);ctx.scale(d,d);ctx.lineCap='round';ctx.lineJoin='round'
}
window.addEventListener('resize',resize);resize();

function ensureScroll(){
  var d=window.devicePixelRatio||1;
  var needed=py+lh+60;
  if(needed>baseH){
    var old=ctx.getImageData(0,0,c.width,c.height);
    baseH=needed;
    c.height=baseH*d;c.style.height=baseH+'px';
    ctx.putImageData(old,0,0);
    ctx.setTransform(1,0,0,1,0,0);ctx.scale(d,d);ctx.lineCap='round';ctx.lineJoin='round';
  }
  window.scrollTo({top:Math.max(0,py-window.innerHeight+120),behavior:'smooth'});
}

function sleep(ms){return new Promise(function(r){setTimeout(r,ms)})}
function drawChar(ch,x,y,clr){ctx.fillStyle=clr||pc;ctx.font='bold 22px \"Segoe UI\",\"Nunito\",system-ui,sans-serif';ctx.textBaseline='top';var w=ctx.measureText(ch).width||cw;ctx.fillText(ch,x+((Math.random()-0.5)*1.2),y+((Math.random()-0.5)*1.2));return w}

window.writeText=async function(t,clr,nl){
  var col=clr||pc;
  if(nl&&t){px=40;py+=lh}
  if(!t)return;
  var dpr=window.devicePixelRatio||1;
  var maxW=window.innerWidth-80;
  var words=t.split(' ');
  for(var wi=0;wi<words.length;wi++){
    var word=words[wi];
    if(word.length===0)continue;
    var wordW=0;
    for(var j=0;j<word.length;j++)wordW+=(ctx.measureText(word[j]).width||cw)+1;
    var spaceW=(wi>0)?(ctx.measureText(' ').width||cw*0.6):0;
    if(px+spaceW+wordW>maxW&&px>60){px=40;py+=lh}
    else if(wi>0)px+=spaceW;
    for(var j=0;j<word.length;j++){
      var ch=word[j],w=drawChar(ch,px,py,col);
      px+=w+1;
      var sx=Math.round((px-14)*dpr),sy=Math.round((py-14)*dpr),sw=Math.ceil(34*dpr),sh=Math.ceil(34*dpr);
      var saved=ctx.getImageData(sx,sy,sw,sh);
      ctx.beginPath();ctx.arc(px,py,ps+3,0,Math.PI*2);ctx.fillStyle=col;ctx.fill();
      ctx.beginPath();ctx.arc(px,py,ps+6,0,Math.PI*2);ctx.strokeStyle=col+'60';ctx.lineWidth=1.5;ctx.stroke();
      await sleep(25);
      ctx.putImageData(saved,sx,sy);
    }
  }
  ensureScroll();
};

window.clearAll=function(){var d=window.devicePixelRatio||1;ctx.clearRect(0,0,c.width/d,c.height/d);px=40;py=40;baseH=0;window.scrollTo({top:0,behavior:'smooth'});resize()};
window.drawLine=function(x1,y1,x2,y2,col){ctx.strokeStyle=col||pc;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke()};
window.drawUnderlineFn=function(y,w,col){ctx.strokeStyle=col||pc;ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(px,y+30);ctx.lineTo(px+w,y+30);ctx.stroke()};
window.drawCircleFn=function(x,y,r,col){ctx.strokeStyle=col||pc;ctx.lineWidth=3;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.stroke()};
window.drawArrowFn=function(x1,y1,x2,y2,col){var clr=col||pc;var hl=10;var ang=Math.atan2(y2-y1,x2-x1);ctx.strokeStyle=clr;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();ctx.beginPath();ctx.moveTo(x2,y2);ctx.lineTo(x2-hl*Math.cos(ang-Math.PI/6),y2-hl*Math.sin(ang-Math.PI/6));ctx.lineTo(x2-hl*Math.cos(ang+Math.PI/6),y2-hl*Math.sin(ang+Math.PI/6));ctx.lineTo(x2,y2);ctx.fillStyle=clr;ctx.fill()};
window.go=function(cmd){if(cmd==='clear')window.clearAll();else if(cmd==='dataurl'){var u=c.toDataURL('image/png');window.parent&&window.parent.postMessage({type:'canvas_data',url:u},'*')}};
window.setPenColor=function(clr){pc=clr||pc};

function gp(e){var r=c.getBoundingClientRect();if(e.touches&&e.touches.length>0)return{x:e.touches[0].clientX-r.left,y:e.touches[0].clientY-r.top};return{x:e.clientX-r.left,y:e.clientY-r.top}}
function st(e){e.preventDefault();drawing=true;var p=gp(e);lx=p.x;ly=p.y;ctx.beginPath();ctx.moveTo(lx,ly)}
function mv(e){e.preventDefault();if(!drawing)return;var p=gp(e);ctx.strokeStyle=pc;ctx.lineWidth=ps;ctx.beginPath();ctx.moveTo(lx,ly);ctx.lineTo(p.x,p.y);ctx.stroke();lx=p.x;ly=p.y}
function en(e){e.preventDefault();drawing=false}
c.addEventListener('mousedown',st);c.addEventListener('mousemove',mv);c.addEventListener('mouseup',en);c.addEventListener('mouseleave',en);
c.addEventListener('touchstart',st,{passive:false});c.addEventListener('touchmove',mv,{passive:false});c.addEventListener('touchend',en);c.addEventListener('touchcancel',en);

window.addEventListener('message',function(e){
  var d=e.data;if(!d||!d.cmd)return;var col=d.color||pc;
  if(d.cmd==='write')window.writeText(d.text||'',col,false);
  else if(d.cmd==='writeln')window.writeText(d.text||'',col,true);
  else if(d.cmd==='clear')window.clearAll();
  else if(d.cmd==='dataurl')window.go('dataurl');
  else if(d.cmd==='penColor')pc=col;
  else if(d.cmd==='line')window.drawLine(d.x1||px,d.y1||py,d.x2||px+50,d.y2||py,col);
  else if(d.cmd==='underline')window.drawUnderlineFn(d.y||py,d.width||100,col);
  else if(d.cmd==='circle')window.drawCircleFn(d.x||px,d.y||py,d.radius||30,col);
  else if(d.cmd==='arrow')window.drawArrowFn(d.x1||px,d.y1||py,d.x2||px+50,d.y2||py,col);
});

window.parent&&window.parent.postMessage({type:'ready'},'*');
</script>
</body>
</html>
`;

export const ARPenCanvas = forwardRef<ARPenCanvasHandle, { color?: string; lineWidth?: number; visible?: boolean }>(
  ({ color = '#00E5FF', lineWidth = 3, visible = true }, ref) => {
    const iframeRef = useRef<any>(null);
    const webViewRef = useRef<any>(null);
    const colorRef = useRef(color);

    const postToCanvas = (msg: any) => {
      try {
        if (isWeb) {
          iframeRef.current?.contentWindow?.postMessage(msg, '*');
        } else {
          const col = msg.color || color;
          const esc = (s: string) => s?.replace(/'/g, "\\'") || '';
          if (msg.cmd === 'write') webViewRef.current?.injectJavaScript(`window.writeText('${esc(msg.text)}','${col}',false); true;`);
          else if (msg.cmd === 'writeln') webViewRef.current?.injectJavaScript(`window.writeText('${esc(msg.text)}','${col}',true); true;`);
          else if (msg.cmd === 'clear') webViewRef.current?.injectJavaScript('window.clearAll(); true;');
          else if (msg.cmd === 'penColor') webViewRef.current?.injectJavaScript(`window.setPenColor('${col}'); true;`);
          else if (msg.cmd === 'line') webViewRef.current?.injectJavaScript(`window.drawLine(${msg.x1||40},${msg.y1||40},${msg.x2||200},${msg.y2||200},'${col}'); true;`);
          else if (msg.cmd === 'dataurl') {
            webViewRef.current?.injectJavaScript('(function(){var u=document.getElementById("c").toDataURL("image/png");window.ReactNativeWebView.postMessage(JSON.stringify({type:"canvas_data",url:u}));})(); true;');
          }
        }
      } catch {}
    };

    useImperativeHandle(ref, () => ({
      write(text, c) { postToCanvas({ cmd: 'write', text, color: c || color }); },
      writeln(text, c) { postToCanvas({ cmd: 'writeln', text, color: c || color }); },
      clearAll() { postToCanvas({ cmd: 'clear' }); },
      getDataUrl(): Promise<string | null> {
        return new Promise((resolve) => {
          const handler = (event: any) => {
            try {
              const d = event.data;
              if (d?.type === 'canvas_data' && d.url) { resolve(d.url); window.removeEventListener('message', handler); }
            } catch {}
          };
          window.addEventListener('message', handler);
          postToCanvas({ cmd: 'dataurl' });
          setTimeout(() => { window.removeEventListener('message', handler); resolve(null); }, 3000);
        });
      },
      drawLine(x1, y1, x2, y2, c) { postToCanvas({ cmd: 'line', x1, y1, x2, y2, color: c || color }); },
      drawUnderline(y, width, c) { postToCanvas({ cmd: 'underline', y, width, color: c || color }); },
      drawCircle(x, y, radius, c) { postToCanvas({ cmd: 'circle', x, y, radius, color: c || color }); },
      drawArrow(x1, y1, x2, y2, c) { postToCanvas({ cmd: 'arrow', x1, y1, x2, y2, color: c || color }); },
      movePen(x, y) { postToCanvas({ cmd: 'movePen', x, y }); },
      setPenColor(c) { colorRef.current = c || color; postToCanvas({ cmd: 'penColor', color: c || color }); },
    }), [color]);

    useEffect(() => { colorRef.current = color; }, [color]);

    if (!visible) return null;

    if (isWeb) {
      return (
        <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 50 }}>
          <iframe
            ref={iframeRef}
            srcDoc={CANVAS_HTML}
            style={{ width: '100%', height: '100%', border: 'none', pointerEvents: 'auto' }}
            title="canvas"
          />
        </View>
      );
    }

    const WebView = require('react-native-webview').WebView;
    return (
      <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 50 }}>
        <WebView
          ref={webViewRef}
          source={{ html: CANVAS_HTML }}
          style={{ flex: 1, backgroundColor: 'transparent' }}
          pointerEvents="auto"
          scrollEnabled={true}
          overScrollMode="always"
          javaScriptEnabled={true}
          domStorageEnabled={false}
          startInLoadingState={false}
          originWhitelist={['*']}
          mixedContentMode="always"
          onError={() => {}}
          onHttpError={() => {}}
          onMessage={(event: any) => {
            try {
              const d = JSON.parse(event.nativeEvent.data);
              if (d?.type === 'canvas_data' && d.url) {
                window.dispatchEvent(new MessageEvent('message', { data: d }));
              }
            } catch {}
          }}
        />
      </View>
    );
  }
);
