import unittest

import user_agent
from reasoning_agent import answers, policy, runtime


class UserAgentFacadeTest(unittest.TestCase):
    def test_root_entrypoint_reexports_internal_contract(self):
        self.assertIs(user_agent.ReasoningAgent, runtime.ReasoningAgent)
        self.assertIs(user_agent.AgentConfig, policy.AgentConfig)
        self.assertIs(user_agent.SUBMISSION_CONFIG, policy.SUBMISSION_CONFIG)
        self.assertIs(user_agent.normalize_answer, answers.normalize_answer)


if __name__ == "__main__":
    unittest.main()
