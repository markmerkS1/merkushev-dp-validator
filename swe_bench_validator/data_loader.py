"""
Data loader for SWE-bench data points.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class DataPointLoader:
    """
    Loader for SWE-bench data points from JSON files.
    """
    
    def __init__(self):
        """Initialize the data loader."""
        pass
    
    def load_data_points_by_files(self, data_points_dir: Path, file_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Load data points from JSON files by file names.
        
        Args:
            data_points_dir: Directory containing data point JSON files
            file_names: Optional list of specific file names to load (without .json extension)
            
        Returns:
            List of data point dictionaries
        """
        logger.info(f"Loading data points from directory: {data_points_dir}")
        
        if not data_points_dir.exists():
            logger.error(f"Data points directory does not exist: {data_points_dir}")
            return []
        
        data_points = []
        
        if file_names is None:
            # Load all files
            json_files = list(data_points_dir.glob("*.json"))
        else:
            # Load only specified files
            json_files = []
            for file_name in file_names:
                # Add .json if not specified
                if not file_name.endswith('.json'):
                    file_name = file_name + '.json'
                
                file_path = data_points_dir / file_name
                if file_path.exists():
                    json_files.append(file_path)
                else:
                    logger.warning(f"Specified file not found: {file_name}")
        
        logger.info(f"Processing {len(json_files)} JSON files")
        
        if not json_files:
            logger.warning("No JSON files found to process")
            return []
        
        for json_file in json_files:
            logger.info(f"Loading data point from file: {json_file.name}")
            data_point = self._load_single_data_point(json_file)
            
            if data_point:
                instance_id = data_point.get("instance_id", "unknown")
                logger.info(f"Loaded data point: {instance_id}")
                data_points.append(data_point)
            else:
                logger.warning(f"Failed to load data point from file: {json_file.name}")
        
        logger.info(f"Total data points loaded: {len(data_points)}")
        return data_points
    
    def _load_single_data_point(self, json_file: Path) -> Optional[Dict[str, Any]]:
        """
        Load a single data point from a JSON file.
        
        Args:
            json_file: Path to JSON file
            
        Returns:
            Data point dictionary or None if loading failed
        """
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data_point = json.load(f)
            
            # Validate the data point
            if self._validate_data_point(data_point):
                return data_point
            else:
                logger.warning(f"Data point validation failed: {json_file.name}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in {json_file.name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading {json_file.name}: {e}")
            return None
    
    def _validate_data_point(self, data_point: Dict[str, Any]) -> bool:
        """
        Validate that a data point has the required fields.
        
        Args:
            data_point: Data point dictionary
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = [
            "instance_id",
            "repo", 
            "base_commit",
            "patch",
            "FAIL_TO_PASS",
            "PASS_TO_PASS"
        ]
        
        # Check required fields
        for field in required_fields:
            if field not in data_point:
                logger.warning(f"Missing required field '{field}' in data point")
                return False
        
        # Validate that patch is not empty
        patch = data_point.get("patch", "")
        if not patch.strip():
            logger.warning("Patch field is empty in data point")
            return False
        
        # Validate that test lists are not empty
        fail_to_pass = data_point.get("FAIL_TO_PASS", [])
        pass_to_pass = data_point.get("PASS_TO_PASS", [])
        
        if not fail_to_pass and not pass_to_pass:
            logger.warning("Both FAIL_TO_PASS and PASS_TO_PASS are empty")
            return False
        
        return True 