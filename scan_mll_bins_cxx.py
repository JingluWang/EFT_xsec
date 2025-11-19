#!/usr/bin/env python3
import re
import subprocess
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent

GENERATE_EVENTS = BASE_DIR / "bin" / "generate_events"

# ---- run_card configuration ----
CARDS_DIR       = BASE_DIR / "Cards"
TEMPLATE_CARD   = CARDS_DIR / "run_card_template.dat"
RUN_CARD        = CARDS_DIR / "run_card.dat"
# ---- param_card configuration ----
PARAM_CARD_TEMPLATE = CARDS_DIR / "param_card_template.dat"
PARAM_CARD          = CARDS_DIR / "param_card.dat"

OUTPUT_FILE     = BASE_DIR / "xsec_vs_mll_cxx.txt"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# --- user configuration ------------------------------------------------------

# List of dilepton mass bins [GeV]
# (m_min, m_max).
MASS_BINS = [
    (15.0, 20.0),
    (20.0, 25.0),
    (25.0, 30.0),
    (30.0, 35.0),
    (35.0, 40.0),
    (40.0, 45.0),
    (45.0, 50.0),
    (50.0, 55.0),
    (55.0, 60.0),
    (60.0, 64.0),
    (64.0, 68.0),
    (68.0, 72.0),
    (72.0, 76.0),
    (76.0, 81.0),
    (81.0, 86.0),
    (86.0, 91.0),
    (91.0, 96.0),
    (96.0, 101.0),
    (101.0, 106.0),
    (106.0, 110.0),
    (110.0, 115.0),
    (115.0, 120.0),
    (120.0, 126.0),
    (126.0, 133.0),
    (133.0, 141.0),
    (141.0, 150.0),
    (150.0, 160.0),
    (160.0, 171.0),
    (171.0, 185.0),
    (185.0, 200.0),
    (200.0, 220.0),
    (220.0, 243.0),
    (243.0, 273.0),
    (273.0, 320.0),
    (320.0, 380.0),
    (380.0, 440.0),
    (440.0, 510.0),
    (510.0, 600.0),
    (600.0, 700.0),
    (700.0, 830.0),
    (830.0, 1000.0),
    (1000.0, 1500.0),
    (1500.0, 3000.0),
]

# Names of the parameters in the run_card:
PARAM_MIN = "mmll"
PARAM_MAX = "mmllmax"

# List of cxx values to scan
CXX_VALUES = [-100, -70, -35, -20, -10, -5, -1, 1, 5, 10, 20, 35, 70, 100]

# Name/comment used for this Wilson coefficient in the param_card
if len(sys.argv) < 2:
    print("Usage: nohup python3 scan_mll_bins_cxx.py <cxx>")
    sys.exit(1)

CXX_LABEL = sys.argv[1]

# -----------------------------------------------------------------------------


def update_run_card(mmin, mmax):
	"""
	Read the template run_card, replace mmll and mmllmax values, and write run_card.dat
	"""
	text = TEMPLATE_CARD.read_text()

	# Regex: replace the number on the line that defines PARAM_MIN and PARAM_MAX
	# Lines look like: "  15.0 = mmll  ! comment"
	pattern_min = rf"^\s*[-+]?[\d.eE+-]+(\s*=\s*{PARAM_MIN}\b)"
	pattern_max = rf"^\s*[-+]?[\d.eE+-]+(\s*=\s*{PARAM_MAX}\b)"

	text, nmin = re.subn(pattern_min, f" {mmin:.6g}\\1", text, flags=re.MULTILINE)
	text, nmax = re.subn(pattern_max, f" {mmax:.6g}\\1", text, flags=re.MULTILINE)

	if nmin == 0 or nmax == 0:
		raise RuntimeError(
			f"Could not find {PARAM_MIN} or {PARAM_MAX} lines in {TEMPLATE_CARD}."
		)

	RUN_CARD.write_text(text)
	print(f"  -> Updated run_card.dat: {PARAM_MIN}={mmin}, {PARAM_MAX}={mmax}")


def update_param_card(cxx_value):
	"""
	Read the template param_card and replace the value of the cxx Wilson coefficient, then write Cards/param_card.dat.
	"""
	text = PARAM_CARD_TEMPLATE.read_text()

	# Pattern: match a line like:
	#   <int>  <number>   # cxx
	# and replace only the <number>
	pattern_cxx = rf"^(\s*\d+\s+)[-+]?[\d.eE+-]+(\s+#\s*{CXX_LABEL}\b)"

	new_text, n = re.subn(
		pattern_cxx,
		lambda m: f"{m.group(1)}{cxx_value:.6e}{m.group(2)}",
		text,
		flags=re.MULTILINE,
	)

	if n == 0:
		raise RuntimeError(
			f"Could not find a line with '# {CXX_LABEL}' in {PARAM_CARD_TEMPLATE}"
		)

	PARAM_CARD.write_text(new_text)
	print(f"  -> Updated param_card.dat: {CXX_LABEL} = {cxx_value}")


def run_madgraph(run_name):
	"""
	Call ./bin/generate_events for a given run_name and capture stdout/stderr into logs/<run_name>.log
	"""
	cmd = [str(GENERATE_EVENTS), run_name, "-f"]
	print("  -> Running:", " ".join(cmd))

	log_path = LOG_DIR / f"{run_name}.log"
	with log_path.open("w") as log:
		subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)

	return log_path


def parse_cross_section(log_path):
	"""
	Parse a generate_events log file to extract the cross section and its error.

	We look for a line like:
	  ' Cross-section :   6.594e+02  +-  3.011e+00 pb'
	"""
	if not log_path.exists():
		raise FileNotFoundError(f"Log file not found: {log_path}")
	
	xsec = None
	err = None
	unit = None

	with log_path.open() as f:
		for line in f:
			# Typical line: "  Cross-section :   1.234e+02 +- 5.67e-01 pb"
			if "Cross-section :" in line:
				parts = line.split()
				# Example indices: ["Cross-section",":","1.234e+02","+-","5.67e-01","pb"]
				try:
					xsec = float(parts[2])
					err = float(parts[4])
					unit = parts[5]
				except Exception as e:
					raise RuntimeError(f"Could not parse cross section from line:\n{line}") from e
				break

	if xsec is None:
		raise RuntimeError(f"Could not find 'Cross-section :' line in {log_path}")

	return xsec, err, unit


def main():
	# Write header
	with OUTPUT_FILE.open("w") as out:
		out.write("# mll_min[GeV]  mll_max[GeV]   cxx    xsec    err    unit\n")

	for i, (mmin, mmax) in enumerate(MASS_BINS, start=1):
		for cxx in CXX_VALUES:
			print(f"\n=== Bin {i}: {mmin} - {mmax} GeV, cxx = {cxx} ===")

			# 1) update run_card.dat
			update_run_card(mmin, mmax)

			# 2) update param_card for this cxx
			update_param_card(cxx)

			# 3) choose a unique run name
			cxx_tag = str(cxx).replace(".", "p").replace("-", "m")
			run_name = f"mll_{int(mmin)}_{int(mmax)}_cxx_{cxx_tag}"

			# 4) run MG
			log_path = run_madgraph(run_name)

			# 5) parse cross section
			xsec, err, unit = parse_cross_section(log_path)
			print(f"  -> Cross-section: {xsec} +- {err} {unit}")

			# 6) append to output text file
			with OUTPUT_FILE.open("a") as out:
				out.write(
					f"{mmin:10.3f} {mmax:10.3f} {cxx:8.3f} "
					f"{xsec:12.6e} {err:12.6e} {unit}\n"
				)

	print("\nAll done. Results in", OUTPUT_FILE)


if __name__ == "__main__":
	main()

