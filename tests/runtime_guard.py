"""Independent Linux verification policy. Not the private office sandbox.

No new privileges, a libseccomp filter and inherited per-process rlimits.
No filesystem Landlock equivalence is claimed. Docker supplies a 2 GiB cgroup
and a read-only root; writable areas are dedicated tmpfs mounts.
"""
import ctypes
import ctypes.util
import errno
import json
import os
from pathlib import Path
import resource
import socket
import sys

class Unverified(RuntimeError):pass
class Comparison(ctypes.Structure):
    _fields_=[('arg',ctypes.c_uint),('op',ctypes.c_int),('a',ctypes.c_uint64),('b',ctypes.c_uint64)]


def install():
    if sys.platform!='linux':raise Unverified('Linux seccomp verification unavailable')
    library=ctypes.util.find_library('seccomp')
    if not library:raise Unverified('libseccomp2 unavailable')
    sec=ctypes.CDLL(library,use_errno=True)
    sec.seccomp_init.argtypes=[ctypes.c_uint32];sec.seccomp_init.restype=ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];sec.seccomp_syscall_resolve_name.restype=ctypes.c_int
    sec.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(Comparison)]
    sec.seccomp_load.argtypes=[ctypes.c_void_p];sec.seccomp_release.argtypes=[ctypes.c_void_p]
    ctx=sec.seccomp_init(0x7fff0000)  # SCMP_ACT_ALLOW
    if not ctx:raise Unverified('seccomp_init failed')
    denied=[]
    def rule(name,action=0x50000|errno.EPERM,comparisons=()):
        number=sec.seccomp_syscall_resolve_name(name.encode())
        if number<0:return
        array=(Comparison*len(comparisons))(*comparisons) if comparisons else None
        rc=sec.seccomp_rule_add_array(ctx,action,number,len(comparisons),array)
        if rc:raise Unverified(f'seccomp rule {name} failed: {rc}')
        denied.append(name)
    try:
        # libseccomp comparisons: NE=1, MASKED_EQ=7.
        for name in ['socket','socketpair']:rule(name,comparisons=[Comparison(0,1,socket.AF_UNIX,0)])
        for name in ['ptrace','mount','umount2','pivot_root','fsopen','fsconfig','fsmount','move_mount','open_tree','mount_setattr','unshare','setns']:
            rule(name)
        # clone3 points to a struct, unreadable to classic seccomp. ENOSYS forces
        # libc pthreads to use clone, whose namespace flags can be checked.
        rule('clone3',0x50000|errno.ENOSYS)
        for flag in [0x80,0x20000,0x2000000,0x4000000,0x8000000,0x10000000,0x20000000,0x40000000]:
            rule('clone',comparisons=[Comparison(0,7,flag,flag)])
        libc=ctypes.CDLL(None,use_errno=True)
        if libc.prctl(38,1,0,0,0)!=0:raise Unverified(f'PR_SET_NO_NEW_PRIVS failed: {ctypes.get_errno()}')
        if sec.seccomp_load(ctx)!=0:raise Unverified(f'seccomp_load failed: {ctypes.get_errno()}')
    finally:sec.seccomp_release(ctx)
    for key,value in [(resource.RLIMIT_CPU,300),(resource.RLIMIT_NOFILE,256),(resource.RLIMIT_FSIZE,256*1024*1024)]:
        resource.setrlimit(key,(value,value))
    return sorted(set(denied))


def probe():
    denied=install()
    unix=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);unix.close()
    for domain in [socket.AF_INET,socket.AF_INET6]:
        try:socket.socket(domain,socket.SOCK_STREAM)
        except OSError as error:assert error.errno==errno.EPERM,error
        else:raise AssertionError('non-UNIX socket allowed')
    libc=ctypes.CDLL(None,use_errno=True)
    for name,args in [('ptrace',(0,0,0,0)),('mount',(None,None,None,0,None)),('unshare',(0x10000000,))]:
        ctypes.set_errno(0)
        assert getattr(libc,name)(*args)==-1 and ctypes.get_errno()==errno.EPERM,name
    assert resource.getrlimit(resource.RLIMIT_CPU)==(300,300)
    assert resource.getrlimit(resource.RLIMIT_NOFILE)==(256,256)
    assert resource.getrlimit(resource.RLIMIT_FSIZE)==(268435456,268435456)
    memory=Path('/sys/fs/cgroup/memory.max')
    if not memory.exists():raise Unverified('cgroup v2 memory.max unavailable')
    assert memory.read_text().strip()==str(2*1024**3),'2 GiB container cgroup not configured'
    # Actually hit FD and file-size limits; CPU/RAM settings are inspected, not
    # exhausted for 300 seconds/2 GiB just to test their existence.
    files=[]
    try:
        while True:files.append(os.open('/dev/null',os.O_RDONLY))
    except OSError as error:assert error.errno==errno.EMFILE,error
    finally:
        for fd in files:os.close(fd)
    file=Path('/output/fsize-probe')
    try:
        with file.open('wb') as stream:
            try:stream.truncate(268435457)
            except OSError as error:assert error.errno==errno.EFBIG,error
            else:raise AssertionError('file-size limit not enforced')
    finally:file.unlink(missing_ok=True)
    status=Path('/proc/self/status').read_text()
    assert 'NoNewPrivs:\t1' in status and 'Seccomp:\t2' in status
    print(json.dumps({'status':'passed','syscall_rules':denied,'sockets':'AF_UNIX only',
                      'ram':'2 GiB aggregate cgroup','cpu':'300 seconds RLIMIT_CPU per process (not exhausted)',
                      'nofile':'256, exhausted and enforced','fsize':'256 MiB, exceeded and enforced',
                      'landlock':'UNVERIFIED: no office_sandbox.py policy available'}))


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--probe']:probe()
        else:
            install()
            os.execv(sys.executable,[sys.executable,*sys.argv[1:]])
    except Unverified as error:
        print(json.dumps({'status':'unverified','message':str(error)}),file=sys.stderr)
        raise SystemExit(3)
