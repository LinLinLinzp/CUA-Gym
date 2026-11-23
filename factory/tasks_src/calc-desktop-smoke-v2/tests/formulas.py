"""Evaluate the arithmetic and conditional sums used by the shift workbook."""

import ast
import math
import operator
import re

from openpyxl.formula import Tokenizer
from openpyxl.formula.tokenizer import TokenizerError
from openpyxl.utils.cell import get_column_letter, range_boundaries


class FormulaError(ValueError):
    pass


def euclidean(value):
    return math.trunc(value)


OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow}
COMPARE = {"=": operator.eq, "<>": operator.ne, "<": operator.lt, ">": operator.gt,
           "<=": operator.le, ">=": operator.ge}
AST_COMPARE = {ast.Eq: "=", ast.NotEq: "<>", ast.Lt: "<", ast.Gt: ">", ast.LtE: "<=", ast.GtE: ">="}
ALLOWED_FUNCTIONS = {"SUMIFS", "COUNTIFS", "SUM", "MIN", "MAX", "INT", "ABS", "QUOTIENT", "IF",
                     "ROUND", "ROUNDDOWN", "ROUNDUP", "TRUNC", "AND", "OR"}
SUPPORTED = (ArithmeticError, TypeError, ValueError, KeyError, IndexError, SyntaxError, TokenizerError, RecursionError)


def test(actual, condition):
    if isinstance(condition, str):
        prefix = re.match(r"^(<=|>=|<>|=|<|>)", condition)
        if prefix:
            comparison, expected = prefix[0], condition[prefix.end():]
        else:
            comparison, expected = "=", condition
        if type(actual) in (int, float):
            try:
                expected = float(expected)
            except ValueError:
                return comparison == "<>"
        elif isinstance(actual, str):
            actual, expected = actual.casefold(), expected.casefold()
        elif actual is None:
            actual = ""
        return COMPARE[comparison](actual, expected)
    return COMPARE["="](actual, condition)


def grouped(arguments):
    if not arguments or len(arguments) % 2:
        raise FormulaError("Invalid conditional ranges")
    filters = list(zip(arguments[::2], arguments[1::2]))
    if not all(type(span) is list for span, _ in filters):
        raise FormulaError("Conditional input must use ranges")
    if len({len(span) for span, _ in filters}) != 1:
        raise FormulaError("Unaligned conditional ranges")
    return [[test(value, condition) for value in span] for span, condition in filters]


def flatten(values):
    return [item for value in values for item in (value if isinstance(value, list) else [value])]


def calculate(function, args):
    if function in ("SUMIFS", "COUNTIFS"):
        if function == "SUMIFS":
            amounts, *arguments = args
        else:
            arguments = args
            amounts = [1] * len(args[0])
        mask = grouped(arguments)
        if type(amounts) is not list or len(amounts) != len(mask[0]):
            raise FormulaError("Unaligned sum range")
        return sum(amount for amount, flags in zip(amounts, zip(*mask))
                   if all(flags) and type(amount) in (int, float))
    if function in ("SUM", "MIN", "MAX"):
        values = [value for value in flatten(args) if type(value) in (int, float)]
        return {"SUM": sum, "MIN": min, "MAX": max}[function](values) if values else 0
    if function == "QUOTIENT":
        return euclidean(args[0] / args[1])
    if function in ("INT", "ABS"):
        return {"INT": math.floor, "ABS": abs}[function](*args)
    if function in ("AND", "OR"):
        return {"AND": all, "OR": any}[function](flatten(args))
    if function in ("ROUND", "ROUNDDOWN", "ROUNDUP", "TRUNC"):
        number = args[0]
        precision = int(args[1]) if len(args) > 1 else 0
        if not -8 <= precision <= 8:
            raise FormulaError("Unsupported precision")
        factor = 10 ** precision
        rounded = {"ROUND": lambda value: math.floor(value + .5), "ROUNDDOWN": math.floor,
                   "ROUNDUP": math.ceil, "TRUNC": math.floor}[function](abs(number) * factor)
        return math.copysign(rounded / factor, number)
    raise FormulaError(f"Unsupported function {function}")


def translate(formula):
    if len(formula) > 4096 or not formula.startswith("="):
        raise FormulaError("Formula text too long or invalid")
    pieces = []
    for token in Tokenizer(formula).items:
        if token.type == "OPERAND" and token.subtype == "RANGE":
            pieces.append(f"CELL({token.value!r})")
        elif token.type == "OPERAND" and token.subtype == "TEXT":
            pieces.append(repr(token.value[1:-1].replace('""', '"')))
        elif token.type == "OPERAND" and token.subtype == "LOGICAL":
            pieces.append(str(token.value.upper() == "TRUE"))
        elif token.type == "OPERATOR-INFIX":
            pieces.append({"=": "==", "<>": "!=", "^": "**"}.get(token.value, token.value))
        elif token.type == "FUNC" and token.subtype == "OPEN":
            name = token.value[:-1].upper().removeprefix("_XLFN.")
            if name not in ALLOWED_FUNCTIONS:
                raise FormulaError(f"Unsupported function {name}")
            pieces.append(name + "(")
        elif token.type in ("OPERAND", "OPERATOR-PREFIX", "PAREN", "FUNC", "SEP", "WHITE-SPACE"):
            pieces.append(token.value)
        else:
            raise FormulaError(f"Unsupported token {token.type}")
    return ast.parse("".join(pieces).strip(), mode="eval").body


class WorkbookFormulas:
    def __init__(self, data, formula_cells, sheet_limits):
        self.data = data
        self.formula_cells = formula_cells
        self.sheet_limits = sheet_limits
        self.cache = {}
        self.active = set()

    def cell(self, sheet, coord):
        key = (sheet, coord)
        if key in self.cache:
            return self.cache[key]
        if key in self.active:
            raise FormulaError("Circular cell reference")
        value = self.data.get(sheet, {}).get(coord)
        if key not in self.formula_cells:
            return value
        self.active.add(key)
        try:
            self.cache[key] = self.eval(sheet, translate(value))
            return self.cache[key]
        finally:
            self.active.remove(key)

    def refs(self, sheet, reference):
        if "!" in reference:
            sheet, reference = reference.rsplit("!", 1)
            sheet = sheet.strip("'").replace("''", "'")
        sheet = next((key for key in self.data if key.casefold() == sheet.casefold()), None)
        if sheet is None:
            raise FormulaError("Unknown sheet")
        reference = reference.replace("$", "").upper()
        c1, r1, c2, r2 = range_boundaries(reference)
        if None in (c1, c2) or c2 - c1 > 10:
            raise FormulaError("Range too wide")
        r1 = r1 if r1 is not None else 1
        r2 = min(r2 if r2 is not None else self.sheet_limits[sheet], 150)
        values = [self.cell(sheet, f"{get_column_letter(col)}{row}")
                  for row in range(r1, r2 + 1) for col in range(c1, c2 + 1)]
        return values if ":" in reference else values[0]

    def eval(self, sheet, node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, str, bool):
            return node.value
        if isinstance(node, ast.BinOp):
            left, right = self.eval(sheet, node.left), self.eval(sheet, node.right)
            if isinstance(node.op, ast.BitAnd):
                result = f"{left}{right}"
                if len(result) > 4096:
                    raise FormulaError("Concatenation too long")
                return result
            if type(left) not in (int, float) or type(right) not in (int, float) or type(node.op) not in OPS:
                raise FormulaError("Expected numeric arithmetic")
            if isinstance(node.op, ast.Pow) and (abs(right) > 20 or abs(left) > 1e9):
                raise FormulaError("Exponent out of range")
            return OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self.eval(sheet, node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            return COMPARE[AST_COMPARE[type(node.ops[0])]](self.eval(sheet, node.left), self.eval(sheet, node.comparators[0]))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            if name == "IF" and len(node.args) == 3:
                decision, yes, no = node.args
                return self.eval(sheet, yes if self.eval(sheet, decision) else no)
            args = [self.eval(sheet, arg) for arg in node.args]
            if name == "CELL":
                return self.refs(sheet, *args)
            return calculate(name, args)
        raise FormulaError("Unsupported formula expression")
