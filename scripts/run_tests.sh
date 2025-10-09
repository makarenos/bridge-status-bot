#!/bin/bash

# Скрипт для запуска тестов с разными опциями

set -e

# Цвета для вывода
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 Running tests...${NC}"

# Опции запуска
COVERAGE=${COVERAGE:-true}
VERBOSE=${VERBOSE:-true}

# Собираем команду pytest
PYTEST_CMD="pytest"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=app --cov-report=html --cov-report=term-missing"
fi

# Запускаем тесты
$PYTEST_CMD tests/

# Если тесты прошли - показываем coverage
if [ $? -eq 0 ] && [ "$COVERAGE" = true ]; then
    echo -e "\n${GREEN}✅ Tests passed!${NC}"
    echo -e "${BLUE}📊 Coverage report: htmlcov/index.html${NC}"
else
    echo -e "\n❌ Tests failed!"
    exit 1
fi