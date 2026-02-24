# verify_code.py
# This script runs inside the sandboxed Docker container.
# It's responsible for performing the "mathematical verification" of the code.

import z3
import sys

# We need to add the app directory to the path to import the generated code
sys.path.insert(0, ".")

from generated_code import new_function

def verify():
    """
    A simple example of formal verification using the Z3 theorem prover.
    It tries to prove that 'new_function()' always returns True.
    """
    print("🔬 Starting mathematical verification...")

    # Define a solver instance from the Z3 library.
    s = z3.Solver()

    # This is the core of the verification logic. We create a logical
    # constraint that represents the *opposite* of what we want to prove.
    # We want to prove `new_function() == True`.
    # So, we ask the solver to find a scenario where `new_function() != True`.
    s.add(new_function() != True)

    # The solver now checks if the constraint is satisfiable ("sat") or
    # unsatisfiable ("unsat").
    result = s.check()

    if result == z3.unsat:
        # If the solver returns "unsat", it means it could not find any
        # possible scenario where `new_function()` is not True.
        # This proves that our property holds.
        print("✅ Verification successful: The property holds.")
        return True
    else:
        # If the solver returns "sat", it found a counterexample that
        # breaks our desired property.
        print("❌ Verification failed: Found a counterexample.")
        # s.model() will show the specific inputs that cause the failure.
        print(s.model())
        return False

if __name__ == "__main__":
    if not verify():
        # If verification fails, exit with a non-zero status code.
        # This will cause the GitHub Actions step to fail, preventing the PR.
        sys.exit(1)
