"""Service for extracting metadata from uploaded datasets."""

import pandas as pd
from typing import Dict, List, Any, Tuple
from pathlib import Path
from app.utils.error_handlers import FileProcessingError


class MetadataExtractor:
    """Extract metadata and statistics from datasets."""
    
    @staticmethod
    async def extract_metadata(file_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Extract comprehensive metadata from a dataset file.
        
        Args:
            file_path: Path to the dataset file
            
        Returns:
            Tuple of (DataFrame, metadata_dict)
            
        Raises:
            FileProcessingError: If file cannot be processed
        """
        try:
            # Load dataset based on file type
            extension = Path(file_path).suffix.lower()
            
            if extension == '.csv':
                df = pd.read_csv(file_path)
            elif extension in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path)
            else:
                raise FileProcessingError(f"Unsupported file type: {extension}")
            
            # Extract metadata
            metadata = {
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": df.columns.tolist(),
                "column_types": MetadataExtractor._get_column_types(df),
                "summary_statistics": MetadataExtractor._get_summary_statistics(df),
                "sample_data": MetadataExtractor._get_sample_data(df),
            }
            
            return df, metadata
            
        except pd.errors.EmptyDataError:
            raise FileProcessingError("The uploaded file is empty")
        except pd.errors.ParserError:
            raise FileProcessingError("Unable to parse the file. Please check the format")
        except Exception as e:
            raise FileProcessingError(f"Error processing file: {str(e)}")
    
    @staticmethod
    def _get_column_types(df: pd.DataFrame) -> Dict[str, str]:
        """
        Get data types for all columns.
        
        Args:
            df: Pandas DataFrame
            
        Returns:
            Dictionary mapping column names to type strings
        """
        type_mapping = {
            'int64': 'integer',
            'float64': 'float',
            'object': 'string',
            'bool': 'boolean',
            'datetime64[ns]': 'datetime',
        }
        
        column_types = {}
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            column_types[col] = type_mapping.get(dtype_str, dtype_str)
        
        return column_types
    
    @staticmethod
    def _get_summary_statistics(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Get summary statistics for numeric columns.
        
        Args:
            df: Pandas DataFrame
            
        Returns:
            Dictionary of column statistics
        """
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
        
        statistics = {}
        for col in numeric_cols:
            statistics[col] = {
                "mean": float(df[col].mean()),
                "median": float(df[col].median()),
                "std": float(df[col].std()),
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "null_count": int(df[col].isnull().sum()),
            }
        
        return statistics
    
    @staticmethod
    def _get_sample_data(df: pd.DataFrame, n: int = 5) -> List[Dict[str, Any]]:
        """
        Get sample rows from the dataset.
        
        Args:
            df: Pandas DataFrame
            n: Number of sample rows
            
        Returns:
            List of dictionaries representing rows
        """
        sample = df.head(n)
        
        # Convert to records and handle NaN values
        records: List[Dict[str, Any]] = [{str(k): v for k, v in row.items()} for row in sample.to_dict('records')]
        
        # Replace NaN with None for JSON serialization
        for record in records:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
        
        return records
    
    @staticmethod
    async def load_dataset(file_path: str) -> pd.DataFrame:
        """
        Load a dataset from file.
        
        Args:
            file_path: Path to dataset file
            
        Returns:
            Pandas DataFrame
            
        Raises:
            FileProcessingError: If file cannot be loaded
        """
        try:
            extension = Path(file_path).suffix.lower()
            
            if extension == '.csv':
                return pd.read_csv(file_path)
            elif extension in ['.xlsx', '.xls']:
                return pd.read_excel(file_path)
            else:
                raise FileProcessingError(f"Unsupported file type: {extension}")
                
        except Exception as e:
            raise FileProcessingError(f"Error loading dataset: {str(e)}")
