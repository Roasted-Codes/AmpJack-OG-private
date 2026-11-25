// lld-link segfaults linking very small PE binaries against the XDK libs.
// A second object file with some real data avoids the crash (same workaround
// as the OXDK d3d/hello sample).
int _ampjack_gip_workaround[1024] = { 0x6D00, 1 };
