from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from app.services.assistant_tools.pydantic_ai_tools import ASSISTANT_TOOLS, AssistantDeps

agent = Agent()


@agent.tool_plain(docstring_format='google', require_parameter_descriptions=True)
def foobar(a: int, b: str, c: dict[str, list[float]]) -> str:
    """Get me foobar.

    Args:
        a: apple pie
        b: banana cake
        c: carrot smoothie
    """
    return f'{a} {b} {c}'


def print_schema(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    for tool in info.function_tools:
        print(tool.name)
        print("="*20)
        print(tool.description)
        print("="*20)
        print(tool.parameters_json_schema)
        print("="*20)
    # tool = info.function_tools[0]
    # print(tool.description)
    # #> Get me foobar.
    # print(tool.parameters_json_schema)
    """
    {
        'additionalProperties': False,
        'properties': {
            'a': {'description': 'apple pie', 'type': 'integer'},
            'b': {'description': 'banana cake', 'type': 'string'},
            'c': {
                'additionalProperties': {'items': {'type': 'number'}, 'type': 'array'},
                'description': 'carrot smoothie',
                'type': 'object',
            },
        },
        'required': ['a', 'b', 'c'],
        'type': 'object',
    }
    """
    return ModelResponse(parts=[TextPart('foobar')])

model=TestModel()
agent=Agent(tools=ASSISTANT_TOOLS,model=FunctionModel(print_schema))

agent.run_sync('hello')