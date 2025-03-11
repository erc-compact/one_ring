import struct
import os

def parse_bestprof(filename):
    info = {}
    if os.path.isfile(filename):
        with open(filename, "r") as f:
            lines = f.readlines()
        
        for ii, line in enumerate(lines):
            if not line.startswith("# "):
                continue
            if line.startswith("# Prob(Noise)"):
                line = line[2:].split("<")
            else:
                line = line[2:].split("=")

            key = line[0].strip()
            value = line[1].strip()

            if "+/-" in value:
                value = value.split("+/-")[0]
                if "inf" in value:
                    value = "0.0"

            if value == "N/A":
                value = "0.0"

            if "Epoch" in key:
                key = key.split()[0]

            if key == "Prob(Noise)":
                key = "Sigma"
                try:
                    value = value.split("(")[1].split()[0].strip("~")
                except:
                    value = "30.0"

            info[key] = value

        basename = os.path.basename(filename)
        info['bestprof_cand_name'] = basename

    return info

def parse_pfd(filename, pointing):
    header_params = [
        "ndms","nperiods","npdots","nsubs","nparts","proflen","nchans","pstep",
        "pdstep","dmstep","ndmfact","npfact","filname","candname","telescope","plotdev",
        "rastr","decstr","dt","tstart","tend","tepoch","bepoch","avgvoverc","lofreq",
        "chan_wid","best_dm","topo_pow","topo_p1","topo_p2","topo_p3","bary_pow","bary_p1",
        "bary_p2","bary_p3","fold_pow","fold_p1","fold_p2","fold_p3","orb_p","orb_e","orb_x",
        "orb_w","orb_t","orb_pd","orb_wd"
    ]
    
    values = {}
    count = 0
    with open(filename, "rb") as f:
        for ii in range(12):
            values[header_params[count]] = struct.unpack("I", f.read(4))[0]
            count += 1
        for ii in range(4):
            val_len = struct.unpack("I", f.read(4))[0]
            values[header_params[count]] = ''.join([char.decode('utf-8') for char in struct.unpack("c"*val_len, f.read(val_len))])
            count += 1
        for ii in range(2):
            values[header_params[count]] = ''.join([char.decode('utf-8') for char in struct.unpack("c"*13, f.read(13))])
            f.seek(3, 1)
            count += 1
        for ii in range(9):
            values[header_params[count]] = struct.unpack("d", f.read(8))[0]
            count += 1
        for ii in range(3):
            values[header_params[count]] = struct.unpack("f", f.read(4))[0]
            count += 1
            f.seek(4, 1)
        for ii in range(3):
            values[header_params[count]] = struct.unpack("d", f.read(8))[0]
            count += 1
    
    basename = os.path.basename(filename)
    # Add any additional processing here

    return values

def merge_two_dicts(x, y):
    z = x.copy()   # start with x's keys and values
    z.update(y)    # modifies z with y's keys and values & returns None
    return z
