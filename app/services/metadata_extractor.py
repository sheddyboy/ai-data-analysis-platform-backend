"""Service for extracting metadata from uploaded datasets."""

import io
import pandas as pd
from typing import Dict, List, Any, Tuple, Union
from pathlib import Path
from app.utils.error_handlers import FileProcessingError


def _open_dataset(file_path_or_key: str) -> Tuple[Union[io.BytesIO, str], str]:
    """
    Return (source, extension) for a dataset identified by an R2 key or local path.

    R2 keys do not start with "/"; legacy local paths do.
    """
    extension = Path(file_path_or_key).suffix.lower()
    if not file_path_or_key.startswith("/"):
        from app.services.storage_service import storage_service
        return storage_service.download(file_path_or_key), extension
    return file_path_or_key, extension


class MetadataExtractor:
    """Extract metadata and statistics from datasets."""

    @staticmethod
    async def extract_metadata(file_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Extract comprehensive metadata from a dataset file.

        Args:
            file_path: R2 object key (e.g. "datasets/uuid.csv") or legacy local path

        Returns:
            Tuple of (DataFrame, metadata_dict)

        Raises:
            FileProcessingError: If file cannot be processed
        """
        try:
            source, extension = _open_dataset(file_path)

            if extension == '.csv':
                df = pd.read_csv(source)
            elif extension in ['.xlsx', '.xls']:
                df = pd.read_excel(source)
            else:
                raise FileProcessingError(f"Unsupported file type: {extension}")

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
        """Get data types for all columns."""
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
        """Get summary statistics for numeric columns."""
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
        """Get sample rows from the dataset."""
        sample = df.head(n)

        records: List[Dict[str, Any]] = [
            {str(k): v for k, v in row.items()}
            for row in sample.to_dict('records')
        ]

        for record in records:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None

        return records

    @staticmethod
    async def load_dataset(file_path: str) -> pd.DataFrame:
        """
        Load a dataset into a DataFrame.

        Args:
            file_path: R2 object key (e.g. "datasets/uuid.csv") or legacy local path

        Returns:
            Pandas DataFrame

        Raises:
            FileProcessingError: If file cannot be loaded
        """
        try:
            source, extension = _open_dataset(file_path)

            if extension == '.csv':
                return pd.read_csv(source)
            elif extension in ['.xlsx', '.xls']:
                return pd.read_excel(source)
            else:
                raise FileProcessingError(f"Unsupported file type: {extension}")

        except Exception as e:
            raise FileProcessingError(f"Error loading dataset: {str(e)}")
