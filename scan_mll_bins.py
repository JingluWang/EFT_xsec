#!/usr/bin/env python3
import re
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

CARDS_DIR       = BASE_DIR / "Cards"
TEMPLATE_CARD   = CARDS_DIR / "run_card_template.dat"
RUN_CARD        = CARDS_DIR / "run_card.dat"
GENERATE_EVENTS = BASE_DIR / "bin" / "generate_events"
OUTPUT_FILE     = BASE_DIR / "xsec_vs_mll.txt"

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

# Template and working run cards
CARDS_DIR     = Path("Cards")
TEMPLATE_CARD = CARDS_DIR / "run_card_template.dat"
RUN_CARD      = CARDS_DIR / "run_card.dat"

# Output text file with cross sections
OUTPUT_FILE = Path("xsec_vs_mll.txt")

# Path to generate_events script (relative to process dir)
GENERATE_EVENTS = Path("bin") / "generate_events"

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
		out.write("# mll_min[GeV]  mll_max[GeV]    xsec    err    unit\n")

	for i, (mmin, mmax) in enumerate(MASS_BINS, start=1):
		print(f"\n=== Bin {i}: {mmin} - {mmax} GeV ===")

		# 1) update run_card.dat
		update_run_card(mmin, mmax)

		# 2) choose a unique run name
		run_name = f"mll_{int(mmin)}_{int(mmax)}"

		# 3) run MG
		log_path = run_madgraph(run_name)

		# 4) parse cross section
		xsec, err, unit = parse_cross_section(log_path)
		print(f"  -> Cross-section: {xsec} +- {err} {unit}")

		# 5) append to output text file
		with OUTPUT_FILE.open("a") as out:
			out.write(f"{mmin:10.3f} {mmax:10.3f} {xsec:12.6e} {err:12.6e} {unit}\n")

	print("\nAll done. Results in", OUTPUT_FILE)


if __name__ == "__main__":
	main()

