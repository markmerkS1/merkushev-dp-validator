#!/usr/bin/env python3
"""
SWE-bench data points validation script
Performs:
1. Loading and formatting data points with model_name="gpt-4"
2. Running docker-compose evaluation
3. Checking results in report.json
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

from swe_bench_validator.data_loader import DataPointLoader
from swe_bench_validator.formatter import PredictionFormatter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SWEBenchValidator:
    """SWE-bench data points validator"""
    
    def __init__(self, data_points_dir: str = "data_points"):
        self.data_points_dir = Path(data_points_dir)
        
        # Create components with correct model_name
        self.loader = DataPointLoader()
        self.formatter = PredictionFormatter(model_name="gpt-4")
    
    def validate_data_points(self, file_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Performs full validation of data points
        
        Args:
            file_names: List of file names for validation (without .json extension)
            
        Returns:
            Validation results
        """
        try:
            # Determine which files to process
            if file_names is None:
                # Get all JSON files in directory
                json_files = list(self.data_points_dir.glob("*.json"))
                file_names = [f.stem for f in json_files]  # stem = name without extension
                logger.info(f"Processing {len(file_names)} files")
            else:
                logger.info(f"Processing {len(file_names)} specified files")
            
            if not file_names:
                return {"error": "No files found for processing"}
            
            # Process each file separately
            all_results = {
                "total_files": len(file_names),
                "successful_files": 0,
                "failed_files": 0,
                "file_results": {}
            }
            
            for file_name in file_names:
                logger.info(f"Processing: {file_name}")
                
                # Validate one file
                file_result = self._validate_single_file(file_name)
                all_results["file_results"][file_name] = file_result
                
                if file_result.get("success", False) and (file_result.get("validation_result", {}).get("status") == "success"):
                    all_results["successful_files"] += 1
                else:
                    all_results["failed_files"] += 1
                    logger.error(f"Failed: {file_name} - {file_result.get('error', 'unknown')}")
            
            # Calculate overall statistics
            success_rate = (all_results["successful_files"] / all_results["total_files"]) * 100 if all_results["total_files"] > 0 else 0
            all_results["success_rate"] = success_rate
            
            return all_results
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {"error": str(e)}
    
    def _validate_single_file(self, file_name: str) -> Dict[str, Any]:
        """
        Validates one file
        
        Args:
            file_name: File name (without .json)
            
        Returns:
            File validation result
        """
        run_id = file_name  # run_id = file name
        predictions_file = f"predictions_{file_name}.jsonl"
        logs_dir = Path("logs/run_evaluation") / run_id / "gpt-4"
        
        try:
            # Step 1: Load data point from specific file
            data_points = self.loader.load_data_points_by_files(self.data_points_dir, [file_name])
            
            if not data_points:
                return {"success": False, "error": f"Failed to load {file_name}.json"}
            
            data_point = data_points[0]
            instance_id = data_point.get("instance_id", "unknown")
            
            # Step 2: Format to predictions
            predictions = self.formatter.convert_to_predictions([data_point])
            
            if not predictions:
                return {"success": False, "error": "Failed to convert to prediction"}
            
            # Step 3: Save prediction to JSONL file
            if not self.formatter.save_predictions_to_file(predictions, predictions_file):
                return {"success": False, "error": "Failed to save prediction"}
            
            # Step 4: Run docker-compose evaluation
            docker_result = self._run_docker_evaluation(predictions_file, run_id)
            
            if not docker_result["success"]:
                return {"success": False, "error": f"Docker evaluation failed: {docker_result['error']}"}
            
            # Step 5: Check results
            validation_result = self._validate_single_result(data_point, logs_dir)
            
            return {
                "success": True,
                "instance_id": instance_id,
                "run_id": run_id,
                "validation_result": validation_result
            }
            
        except Exception as e:
            logger.error(f"Error validating {file_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_docker_evaluation(self, predictions_file: str, run_id: str) -> Dict[str, Any]:
        """Runs docker-compose evaluation"""
        
        cmd = [
            "docker","compose", "run", "--rm", "swe-bench-validator",
            "python", "-m", "swebench.harness.run_evaluation",
            "--predictions_path", predictions_file,
            "--run_id", run_id,
            "--dataset_name", "SWE-bench/SWE-bench",
            "--clean", "True"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            if result.returncode == 0:
                return {"success": True}
            else:
                return {"success": False, "error": f"Exit code: {result.returncode}"}
                
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _validate_single_result(self, data_point: Dict[str, Any], logs_dir: Path) -> Dict[str, Any]:
        """Checks result for one data point"""
        
        instance_id = data_point["instance_id"]
        
        # Parse expected tests from data point
        expected_fail_to_pass = json.loads(data_point["FAIL_TO_PASS"])
        expected_pass_to_pass = json.loads(data_point["PASS_TO_PASS"])
        
        # Find report.json for this instance
        report_path = logs_dir / instance_id / "report.json"
        
        if not report_path.exists():
            return {
                "status": "report_not_found",
                "error": f"File {report_path} not found"
            }
        
        # Read report.json
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                report = json.load(f)
            
            # Extract test results
            instance_report = report.get(instance_id, {})
            tests_status = instance_report.get("tests_status", {})
            
            actual_fail_to_pass = tests_status.get("FAIL_TO_PASS", {}).get("success", [])
            actual_pass_to_pass = tests_status.get("PASS_TO_PASS", {}).get("success", [])
            
            # Check correspondence
            fail_to_pass_match = set(expected_fail_to_pass) == set(actual_fail_to_pass)
            pass_to_pass_match = set(expected_pass_to_pass) == set(actual_pass_to_pass)
            
            is_resolved = instance_report.get("resolved", False)
            
            if fail_to_pass_match and pass_to_pass_match and is_resolved:
                status = "success"
            else:
                status = "test_mismatch"
            
            return {
                "status": status,
                "resolved": is_resolved,
                "fail_to_pass_match": fail_to_pass_match,
                "pass_to_pass_match": pass_to_pass_match,
                "expected_fail_to_pass": expected_fail_to_pass,
                "actual_fail_to_pass": actual_fail_to_pass,
                "expected_pass_to_pass": expected_pass_to_pass,
                "actual_pass_to_pass": actual_pass_to_pass
            }
            
        except Exception as e:
            return {
                "status": "read_error",
                "error": str(e)
            }
    
    def print_results(self, results: Dict[str, Any]) -> None:
        """Prints validation results"""
        
        print("\n" + "="*60)
        print("SWE-bench Validation Results")
        print("="*60)
        
        if "error" in results:
            print(f"Validation failed: {results['error']}")
            return
        
        total_files = results.get("total_files", 0)
        successful_files = results.get("successful_files", 0)
        failed_files = results.get("failed_files", 0)
        success_rate = results.get("success_rate", 0.0)
        
        print(f"Total files: {total_files}")
        print(f"Successful: {successful_files}")
        print(f"Failed: {failed_files}")
        print(f"Success rate: {success_rate:.1f}%")
        
        # Detailed results by files
        file_results = results.get("file_results", {})
        if file_results:
            print(f"\nDetailed results:")
            
            for file_name, file_result in file_results.items():
                if file_result.get("success", False):
                    validation_result = file_result.get("validation_result", {})
                    instance_id = file_result.get("instance_id", "unknown")
                    status = validation_result.get("status", "unknown")
                    
                    if status == "success":
                        print(f"  {file_name} ({instance_id}): All tests passed")
                    elif status == "test_mismatch":
                        print(f"  {file_name} ({instance_id}): Some tests failed")
                    elif status == "report_not_found":
                        print(f"  {file_name} ({instance_id}): Report not found")
                    elif status == "read_error":
                        print(f"  {file_name} ({instance_id}): Error reading report")
                    else:
                        print(f"  {file_name} ({instance_id}): Unknown status")
                else:
                    error = file_result.get("error", "unknown")
                    print(f"  {file_name}: {error}")
        
        # Final verdict
        if success_rate == 100.0:
            print(f"\n All files processed successfully!")
        elif success_rate >= 80.0:
            print(f"\n Most files processed successfully")
        elif success_rate >= 50.0:
            print(f"\n Half of files processed")
        else:
            print(f"\n Most files failed")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="SWE-bench data points validation")
    parser.add_argument("--data-points-dir", default="data_points", 
                       help="Directory with data point JSON files")
    parser.add_argument("--instance-ids", nargs="+", 
                       help="Specific file names for validation (without .json extension)")
    parser.add_argument("--verbose", action="store_true", 
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create validator
    validator = SWEBenchValidator(
        data_points_dir=args.data_points_dir
    )
    
    # Run validation
    results = validator.validate_data_points(args.instance_ids)
    
    # Print results
    validator.print_results(results)
    
    # Return exit code
    if "error" in results:
        sys.exit(1)
    elif results.get("success_rate", 0) == 100.0:
        sys.exit(0)  # Full success
    else:
        sys.exit(1)  # Partial success or failure


if __name__ == "__main__":
    main() 