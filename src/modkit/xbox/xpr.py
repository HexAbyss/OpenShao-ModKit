"""XPR0 (Xbox packed resource) parsing and Xbox texture decoding (level 0) to RGBA with numpy, and the 64-bit hash that names a texture."""
import struct,numpy as np
M64=(1<<64)-1
def xhash(b,seed=1469598103934665603):
    k0=0x9E3779B97F4A7C15;k1=0xE7037ED1A0B428DB
    mix=lambda a,c:((a*c)&M64)^((a*c)>>64)
    n=len(b);s=(seed^k0)&M64;i=0
    while i+16<=n:
        x,y=struct.unpack_from('<QQ',b,i);s=mix(x^k1,(y^s)&M64);i+=16
    r=n-i
    if r:
        if r>=8:x=struct.unpack_from('<Q',b,i)[0];y=struct.unpack_from('<Q',b,n-8)[0]
        else:x=int.from_bytes(b[i:i+r],'little');y=0
        s=mix(x^k1,(y^s^r)&M64)
    return mix((s^k0)&M64,(n^k1)&M64)
FMT={0x00:('L8',8),0x01:('AL8',8),0x02:('A1R5G5B5',16),0x03:('X1R5G5B5',16),0x04:('A4R4G4B4',16),0x05:('R5G6B5',16),
 0x06:('A8R8G8B8',32),0x07:('X8R8G8B8',32),0x0B:('P8',8),0x0C:('DXT1',4),0x0E:('DXT3',8),0x0F:('DXT5',8),
 0x10:('LIN_A1R5G5B5',16),0x11:('LIN_R5G6B5',16),0x12:('LIN_A8R8G8B8',32),0x13:('LIN_L8',8),0x19:('A8',8),0x1A:('A8L8',16),
 0x1E:('LIN_X8R8G8B8',32),0x1D:('LIN_A4R4G4B4',16),0x3A:('A8B8G8R8',32),0x3C:('R8G8B8A8',32),0x38:('R5G5B5A1',16),0x39:('R4G4B4A4',16)}
def level0_size(f,w,h):
    n,bits=FMT[f]
    if n.startswith('DXT'):return max(1,(w+3)//4)*max(1,(h+3)//4)*bits*2 if False else max(1,(w+3)//4)*max(1,(h+3)//4)*(8 if n=='DXT1' else 16)
    return w*h*bits//8
def parse_xpr(b):
    """-> list of (resource dict, level0 raw bytes) for texture resources"""
    if b[:4]!=b'XPR0':return []
    total,hs=struct.unpack_from('<II',b,4);out=[];p=12
    while p+20<=hs and struct.unpack_from('<I',b,p)[0]!=0xFFFFFFFF:
        common,data,lock,fmt,size=struct.unpack_from('<5I',b,p);p+=20
        if common&0x70000!=0x40000:continue
        f=(fmt>>8)&0xFF;cube=bool(fmt&4)
        if size:w=(size&0xFFF)+1;h=((size>>12)&0xFFF)+1;lin=True;pitch=((size>>24)+1)*64
        else:w=1<<((fmt>>20)&0xF);h=1<<((fmt>>24)&0xF);lin=False;pitch=0
        if f not in FMT:out.append((dict(fmt=f,w=w,h=h,cube=cube,levels=(fmt>>16)&0xF,unknown=True),b''));continue
        sz=pitch*h if lin else level0_size(f,w,h)
        raw=bytes(b[hs+data:hs+data+sz])
        out.append((dict(fmt=f,name=FMT[f][0],w=w,h=h,cube=cube,lin=lin,pitch=pitch,levels=(fmt>>16)&0xF,rawfmt=fmt),raw))
    return out
def _deposit(v,mask):
    r=0;bit=1
    while mask:
        low=mask&-mask
        if v&bit:r|=low
        mask&=mask-1;bit<<=1
    return r
def _swz(w,h):
    mx=my=0;bit=1;lx=(w-1).bit_length();ly=(h-1).bit_length()
    for i in range(max(lx,ly)):
        if i<lx:mx|=bit;bit<<=1
        if i<ly:my|=bit;bit<<=1
    return mx,my
def unswizzle(raw,w,h,bpp):
    mx,my=_swz(w,h)
    xo=np.array([_deposit(x,mx) for x in range(w)]);yo=np.array([_deposit(y,my) for y in range(h)])
    idx=(yo[:,None]|xo[None,:])
    a=np.frombuffer(raw,np.uint8).reshape(-1,bpp)
    return a[idx.ravel()].reshape(h,w,bpp)
def _c565(c):
    r=((c>>11)&31)*255//31;g=((c>>5)&63)*255//63;b=(c&31)*255//31;return np.stack([r,g,b],-1).astype(np.uint8)
def dxt(raw,w,h,kind):
    bw,bh=max(1,(w+3)//4),max(1,(h+3)//4);bs=8 if kind=='DXT1' else 16
    a=np.frombuffer(raw[:bw*bh*bs],np.uint8).reshape(bh*bw,bs)
    cb=a[:,-8:].copy();c0=cb[:,0].astype(np.uint16)|(cb[:,1].astype(np.uint16)<<8);c1=cb[:,2].astype(np.uint16)|(cb[:,3].astype(np.uint16)<<8)
    p0=_c565(c0).astype(np.int32);p1=_c565(c1).astype(np.int32)
    opaque=(c0>c1)|(kind!='DXT1')
    pal=np.zeros((len(a),4,4),np.int32);pal[:,0,:3]=p0;pal[:,1,:3]=p1;pal[:,:,3]=255
    o=opaque[:,None]
    pal[:,2,:3]=np.where(o,(2*p0+p1)//3,(p0+p1)//2);pal[:,3,:3]=np.where(o,(p0+2*p1)//3,0)
    pal[:,3,3]=np.where(o[:,0]|(kind!='DXT1'),255,0)
    bits=cb[:,4].astype(np.uint32)|(cb[:,5].astype(np.uint32)<<8)|(cb[:,6].astype(np.uint32)<<16)|(cb[:,7].astype(np.uint32)<<24)
    sel=np.stack([(bits>>(2*i))&3 for i in range(16)],1)
    px=pal[np.arange(len(a))[:,None],sel]            # n,16,4
    if kind=='DXT3':
        ab=a[:,:8];al=np.stack([ab[:,i//2]>>(4*(i%2))&15 for i in range(16)],1)*17;px[:,:,3]=al
    if kind=='DXT5':
        a0=a[:,0].astype(np.int32);a1=a[:,1].astype(np.int32)
        ab=a[:,2:8].astype(np.uint64);v=np.zeros(len(a),np.uint64)
        for i in range(6):v|=ab[:,i]<<np.uint64(8*i)
        ai=np.stack([((v>>np.uint64(3*i))&np.uint64(7)).astype(np.int32) for i in range(16)],1)
        t=np.zeros((len(a),8),np.int32);t[:,0]=a0;t[:,1]=a1
        gt=(a0>a1)
        for k in range(1,7):
            t[:,k+1]=np.where(gt,((7-k)*a0+k*a1)//7,0)
        for k in range(1,5):
            t[:,k+1]=np.where(gt,t[:,k+1],((5-k)*a0+k*a1)//5)
        t[:,6]=np.where(gt,t[:,6],0);t[:,7]=np.where(gt,t[:,7],255)
        px[:,:,3]=t[np.arange(len(a))[:,None],ai]
    img=px.reshape(bh,bw,4,4,4).transpose(0,2,1,3,4).reshape(bh*4,bw*4,4)
    return img[:h,:w].astype(np.uint8)
def to_rgba(info,raw):
    f=info['fmt'];n=info['name'];w,h=info['w'],info['h']
    if n.startswith('DXT'):return dxt(raw,w,h,n)
    bits=FMT[f][1];bpp=bits//8
    if info['lin']:
        a=np.frombuffer(raw,np.uint8)[:info['pitch']*h].reshape(h,info['pitch'])[:,:w*bpp].reshape(h,w,bpp)
    else:a=unswizzle(raw,w,h,bpp)
    if n in('A8R8G8B8','LIN_A8R8G8B8'):return a[...,[2,1,0,3]]
    if n in('X8R8G8B8','LIN_X8R8G8B8'):x=a[...,[2,1,0,3]].copy();x[...,3]=255;return x
    # The names list the channels from the most significant byte of the little-endian dword down, as in A8R8G8B8 (bytes B,G,R,A in memory).
    # No texture of the supported game uses these two formats; the mapping follows that rule and is covered by a unit test.
    if n in('A8B8G8R8',):return a[...,[0,1,2,3]]
    if n in('R8G8B8A8',):return a[...,[3,2,1,0]]
    if n in('L8','LIN_L8'):g=a[...,0];return np.stack([g,g,g,np.full_like(g,255)],-1)
    if n=='AL8':g=a[...,0];return np.stack([g,g,g,g],-1)
    if n=='A8':g=a[...,0];return np.stack([np.full_like(g,255)]*3+[g],-1)
    if n=='A8L8':return np.stack([a[...,0]]*3+[a[...,1]],-1)
    v=a[...,0].astype(np.uint16)|(a[...,1].astype(np.uint16)<<8)
    if n in('R5G6B5','LIN_R5G6B5'):return np.concatenate([_c565(v),np.full((h,w,1),255,np.uint8)],-1)
    if n in('A1R5G5B5','LIN_A1R5G5B5','X1R5G5B5'):
        r=((v>>10)&31)*255//31;g=((v>>5)&31)*255//31;b=(v&31)*255//31;al=np.where((v>>15)&1,255,0) if n!='X1R5G5B5' else 255+0*v
        return np.stack([r,g,b,al],-1).astype(np.uint8)
    if n in('A4R4G4B4','LIN_A4R4G4B4'):
        return np.stack([((v>>8)&15)*17,((v>>4)&15)*17,(v&15)*17,((v>>12)&15)*17],-1).astype(np.uint8)
    return None
