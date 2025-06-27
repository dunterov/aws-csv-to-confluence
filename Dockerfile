# Use official Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy pyproject.toml and poetry.lock first to cache dependencies
COPY pyproject.toml ./

# Install poetry
RUN pip install poetry

# Install dependencies
RUN poetry config virtualenvs.create false && poetry install --no-root

# Copy the rest of the code
COPY . .

# Run the main script
ENTRYPOINT ["python", "-m", "aws_csv_to_confluence.main"]
CMD []