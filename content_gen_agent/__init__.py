"""Nablix Content Generation Agent.

Generates a complete 24-table content package for a maths topic from a
formatted source document.

Modules, in dependency order:

    table_schemas   CG-001  the 24 table definitions extracted from the
                            reference workbook: column order, types, enums,
                            foreign keys and ID patterns
    models          CG-002  Pydantic row models and the intermediate
                            package contracts between generation stages
    id_service      CG-003  deterministic, collision-free ID generation
"""
