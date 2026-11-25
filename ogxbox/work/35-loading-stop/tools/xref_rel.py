import struct,sys
m=open(sys.argv[1],'rb').read();B=0x412000
for t in map(lambda s:int(s,16),sys.argv[2:]):
    print(hex(t),[hex(B+p) for p in range(len(m)-5) if m[p] in(0xe8,0xe9) and B+p+5+struct.unpack_from('<i',m,p+1)[0]==t])
